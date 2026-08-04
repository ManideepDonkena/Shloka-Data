"""CTC forced alignment of a BrajaBeats recitation, via Meta's MMS aligner.

This is not speech recognition: we already know the exact text, so the model only
has to decide *where* each word sits. A fixed-weight acoustic model emits
per-frame character posteriors and Viterbi finds the single optimal text->audio
path. Deterministic -- no sampling, same input gives the same output.

The recordings contain the verse twice (a line-paced pass, then a slow
word-by-word pass with call-and-response echoes). MMS has a `*` star token that
absorbs audio not covered by the transcript, so aligning `words + [*]` pins the
words to the first pass and lets the star swallow everything after it.

    .venv/bin/python align_mms.py --eval          score against the hand tags
    .venv/bin/python align_mms.py --one 1 14      one verse, verbose
    .venv/bin/python align_mms.py --all [limit]   write aligned_data.json
"""
import json, os, re, sys, unicodedata
import numpy as np
import torch, torchaudio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gapdetect import decode
from sandhi_map import build as sandhi_build, FOLD

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
BRAJA = os.path.join(REPO, "BrajaBeats_Gita_MP3")
SR = 16000
VOWELS = re.compile(r"(ai|au|[aāiīuūṛṝḷeo])")

_bundle = _model = _tok = _aligner = None
DEVICE = ("cuda" if (os.environ.get("ALIGN_DEVICE", "auto") != "cpu"
                     and torch.cuda.is_available()) else "cpu")


def load_model():
    """Loads once; first call downloads ~1.2 GB of MMS weights."""
    global _bundle, _model, _tok, _aligner
    if _model is None:
        _bundle = torchaudio.pipelines.MMS_FA
        _model = _bundle.get_model().eval().to(DEVICE)
        _tok = _bundle.get_tokenizer()
        _aligner = _bundle.get_aligner()
    return _bundle, _model, _tok, _aligner


def romanize(word):
    """IAST -> the aligner's roman charset (a-z plus apostrophe)."""
    s = unicodedata.normalize("NFC", word.lower())
    s = re.sub(r"^[’ʼ'`]", "a", s)          # avagraha = elided a-
    s = "".join(FOLD.get(c, c) for c in s)
    s = re.sub(r"[^a-z]", "", s)
    return s


def syllables(w):
    return max(1, len(VOWELS.findall(w.lower())))


def resolve(audio_path, use_vocals):
    """Optionally swap in the Demucs vocal stem, if one has been cached."""
    if not use_vocals:
        return audio_path
    base = os.path.splitext(os.path.basename(audio_path))[0]
    stem = os.path.join(ROOT, "vocals", base + ".wav")
    return stem if os.path.exists(stem) else audio_path


def align_words(audio_path, words, star_tail=True, use_vocals=False):
    """Returns [(start_s, end_s, score), ...] aligned to the FIRST occurrence."""
    bundle, model, tok, aligner = load_model()
    y = decode(resolve(audio_path, use_vocals), sr=SR)
    wav = torch.from_numpy(y.copy()).unsqueeze(0)

    roman = [romanize(w) for w in words]
    keep = [i for i, r in enumerate(roman) if r]
    seq = [roman[i] for i in keep]
    if not seq:
        return None, None

    # `*` before and after: absorb the intro music and the whole second pass
    trans = (["*"] + seq + ["*"]) if star_tail else seq

    with torch.inference_mode():
        emission, _ = model(wav.to(DEVICE))
    ratio = wav.shape[1] / emission.shape[1] / SR      # seconds per emission frame

    spans = aligner(emission[0].cpu(), tok(trans))
    if star_tail:
        spans = spans[1:-1]

    out, k = [], 0
    res = [None] * len(words)
    for idx, sp in zip(keep, spans):
        if not sp:
            continue
        a = sp[0].start * ratio
        b = sp[-1].end * ratio
        sc = float(np.mean([t.score for t in sp]))
        res[idx] = (a, b, sc)

    # words dropped by romanisation borrow their neighbour's edge
    for i, r in enumerate(res):
        if r is None:
            prev = res[i - 1] if i else None
            res[i] = (prev[1], prev[1] + 0.05, 0.0) if prev else (0.0, 0.05, 0.0)
    return res, float(emission.shape[1] * ratio)


def vocal_env(y):
    """Same voice-biased envelope the tag editor draws, at 100 fps."""
    from gapdetect import stft_mag, smooth, NFFT, HOP
    S = stft_mag(y)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (f >= 300) & (f <= 3500)
    floor = np.percentile(S, 15, axis=0, keepdims=True)
    resid = np.maximum(S - floor, 1e-8)
    db = 20 * np.log10(np.sqrt((resid[:, band] ** 2).mean(axis=1)) + 1e-8)
    return smooth(db, 9)


def snap_boundaries(spans, env, win=0.35, fps=100.0):
    """CTC fires on the character peak, so a sustained chant vowel gets cut
    short. The aligner is authoritative about WHICH word is where; the energy
    envelope is authoritative about WHERE the voice actually stops. Combine:
    move each boundary onto the nearby low-energy valley."""
    n = len(env)
    out = [list(s) for s in spans]

    def valley(lo, hi):
        i0, i1 = max(0, int(lo * fps)), min(n, int(hi * fps))
        if i1 - i0 < 2:
            return None
        seg = env[i0:i1]
        thr = seg.min() + 0.20 * (seg.max() - seg.min())
        below = np.flatnonzero(seg <= thr)
        if not len(below):
            return None
        # widest contiguous run at the bottom
        runs, start = [], below[0]
        for a, b in zip(below, below[1:]):
            if b != a + 1:
                runs.append((start, a)); start = b
        runs.append((start, below[-1]))
        a, b = max(runs, key=lambda r: r[1] - r[0])
        return (i0 + a) / fps, (i0 + b) / fps

    # inter-word gaps
    for i in range(len(out) - 1):
        e, s2 = out[i][1], out[i + 1][0]
        v = valley(min(e, s2) - win, max(e, s2) + win)
        if v and v[0] > out[i][0] + 0.08 and v[1] < out[i + 1][1] - 0.08:
            out[i][1], out[i + 1][0] = v

    # leading edge and trailing edge
    first, last = out[0], out[-1]
    v = valley(max(0, first[0] - win), first[0] + win * 0.6)
    if v and v[1] < first[1] - 0.10:
        first[0] = v[1]
    v = valley(last[1] - win * 0.6, last[1] + win)
    if v and v[0] > last[0] + 0.10:
        last[1] = v[0]

    for a in out:
        if a[1] - a[0] < 0.06:
            a[1] = a[0] + 0.06
    return [tuple(a) for a in out]


def caesura(toks):
    syl = [syllables(t) for t in toks]
    tot, run, best, bi = sum(syl), 0, 1e9, 1
    for i in range(1, len(toks)):
        run += syl[i - 1]
        if abs(run - tot / 2) < best:
            best, bi = abs(run - tot / 2), i
    return bi


def analyse(audio_path, verse, snap=True, use_vocals=False):
    lines, tokens, tok_line, syns, path, _c = sandhi_build(verse)
    meaning = {}
    for si, ti, _r, _f in path:
        key = " + ".join(syns[k] for k in si)
        mean = " / ".join(verse["synonyms"][syns[k]]["meaning"] for k in si)
        for t in ti:
            meaning[t] = (key, mean)

    spans, _dur = align_words(audio_path, tokens, use_vocals=use_vocals)
    if spans is None:
        return None
    if snap:
        env = vocal_env(decode(resolve(audio_path, use_vocals), sr=SR))
        raw = [(a, b) for a, b, _ in spans]
        snapped = snap_boundaries(raw, env)
        spans = [(sa, sb, sc) for (sa, sb), (_, _, sc) in zip(snapped, spans)]

    out_lines, scores = [], []
    ti0 = 0
    for li, ln in enumerate(lines):
        toks = ln.split()
        idx = list(range(ti0, ti0 + len(toks)))
        la, lb = spans[idx[0]][0], spans[idx[-1]][1]
        rec = {"index": li, "text": ln,
               "line_audio": {"start": round(la, 3), "end": round(lb, 3)},
               "chunks": []}
        groups = ([toks[:caesura(toks)], toks[caesura(toks):]]
                  if len(toks) >= 2 else [toks])
        g0 = 0
        for grp in groups:
            gidx = idx[g0:g0 + len(grp)]
            ca, cb = spans[gidx[0]][0], spans[gidx[-1]][1]
            chunk = {"text": " ".join(grp),
                     "chunk_audio": {"start": round(ca, 3), "end": round(cb, 3)},
                     "split_method": "mms", "words": []}
            for j, tk in enumerate(grp):
                t = gidx[j]
                a, b, sc = spans[t]
                key, mean = meaning.get(t, ("", ""))
                scores.append(sc)
                chunk["words"].append({
                    "token": tk, "synonym": key, "meaning": mean,
                    "word_audio": {"start": round(a, 3), "end": round(b, 3)},
                    "score": round(sc, 3), "exact": True})
            g0 += len(grp)
            rec["chunks"].append(chunk)
        ti0 += len(toks)
        out_lines.append(rec)

    return {"lines": out_lines,
            "confidence": round(float(np.mean(scores)) if scores else 0.0, 3),
            "verse_audio": {"start": out_lines[0]["line_audio"]["start"],
                            "end": out_lines[-1]["line_audio"]["end"]}}


# ---------------- modes ----------------
def _verse(gita, ch, sh):
    return next(v for v in gita if v["chapter"] == ch and v["shloka"] == sh)


def show_one(ch, sh):
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    res = analyse(os.path.join(BRAJA, f"Bhagavad-gita {ch}.{sh}.mp3"), _verse(gita, ch, sh))
    print(f"BG {ch}.{sh}  confidence {res['confidence']}")
    for L in res["lines"]:
        a, b = L["line_audio"]["start"], L["line_audio"]["end"]
        print(f"  L{L['index']} {a:6.2f}-{b:6.2f}  {L['text']}")
        for C in L["chunks"]:
            for w in C["words"]:
                wa = w["word_audio"]
                print(f"       {w['token']:<20} {wa['start']:6.2f}-{wa['end']:6.2f}"
                      f"  ({wa['end']-wa['start']:.2f}s)  score {w['score']:.2f}")


def evaluate(use_vocals=False):
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    print("input:", "Demucs vocal stem" if use_vocals else "original mix")
    for ch, sh, tag, mp3 in [("1", "14", "tagged_gita_1_14.json", "Bhagavad-gita 1.14.mp3"),
                             ("18", "66", "tagged_gita_18_66.json", "Bhagavad-gita 18.66.mp3")]:
        verse = _verse(gita, ch, sh)
        res = analyse(os.path.join(BRAJA, mp3), verse, use_vocals=use_vocals)
        lines = [l.strip() for l in verse["english"].split("\n") if l.strip()]
        gt = [(s["start"]/1000, s["end"]/1000) for s in
              json.load(open(os.path.join(REPO, tag)))["segments"]
              if s["label"].strip() in lines]
        gt.sort()
        print(f"\n=== BG {ch}.{sh}   confidence {res['confidence']} ===")
        errs = []
        for i, L in enumerate(res["lines"]):
            a, b = L["line_audio"]["start"], L["line_audio"]["end"]
            if i < len(gt):
                ga, gb = gt[i]
                es, ee = abs(a-ga)*1000, abs(b-gb)*1000
                errs += [es, ee]
                print(f"  L{i} mms {a:6.2f}-{b:6.2f}  hand {ga:6.2f}-{gb:6.2f}"
                      f"   err {es:5.0f}/{ee:5.0f} ms   {L['text']}")
        if errs:
            print(f"  line boundary error: median {np.median(errs):.0f} ms  "
                  f"mean {np.mean(errs):.0f} ms  max {np.max(errs):.0f} ms")
        sc = [w["score"] for L in res["lines"] for C in L["chunks"] for w in C["words"]]
        print(f"  per-word score: min {min(sc):.2f}  median {np.median(sc):.2f}")


def run_all(limit=None, use_vocals=False):
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    index = {f"{v['chapter']}.{v['shloka']}": v for v in gita}
    files = sorted(f for f in os.listdir(BRAJA) if f.lower().endswith(".mp3"))
    out, skipped = [], []
    for n, fn in enumerate(files):
        if limit and len(out) >= limit:
            break
        m = re.search(r"(\d+)\.(\d+)", fn)
        if not m:
            skipped.append((fn, "no chapter.verse")); continue
        vid = f"{m.group(1)}.{m.group(2)}"
        verse = index.get(vid)
        if verse is None:
            skipped.append((fn, f"{vid} not in gita.json")); continue
        try:
            res = analyse(os.path.join(BRAJA, fn), verse, use_vocals=use_vocals)
        except Exception as exc:
            skipped.append((fn, f"error: {exc}")); continue
        if res is None:
            skipped.append((fn, "no alignment")); continue
        out.append({"id": vid, "chapter": m.group(1), "shloka": m.group(2),
                    "audio": "braja/" + fn, "source_file": fn,
                    "sanskrit": verse.get("sanskrit", ""),
                    "translation": verse.get("translation", ""),
                    "align_cost": 0.0, "auto": True, "aligner": "mms",
                    "confidence": res["confidence"],
                    "verse_audio": res["verse_audio"], "lines": res["lines"],
                    "synonyms": [{"key": k, "meaning": v["meaning"]}
                                 for k, v in verse["synonyms"].items()]})
        if (n + 1) % 20 == 0:
            print(f"  … {n+1}/{len(files)}", flush=True)

    out.sort(key=lambda v: (int(v["chapter"]), int(v["shloka"])))
    name = "aligned_vocals.json" if use_vocals else "aligned_data.json"
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {name}: {len(out)} verses, {len(skipped)} skipped")
    if out:
        c = np.array([v["confidence"] for v in out])
        for t in (0.8, 0.6, 0.4):
            print(f"  confidence >= {t}: {(c>=t).sum()} ({(c>=t).mean()*100:.0f}%)")
        print(f"  median {np.median(c):.2f}  min {c.min():.2f}")


if __name__ == "__main__":
    a = sys.argv
    if "--eval" in a:
        evaluate(use_vocals="--vocals" in a)
    elif "--one" in a:
        i = a.index("--one"); show_one(a[i+1], a[i+2])
    elif "--all" in a:
        i = a.index("--all")
        run_all(int(a[i+1]) if len(a) > i+1 and a[i+1].isdigit() else None,
                use_vocals="--vocals" in a)
    else:
        print(__doc__)
