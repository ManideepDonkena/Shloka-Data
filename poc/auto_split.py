"""Deterministic hierarchical split of a BrajaBeats recitation.

No ML. The verse text supplies the counts, and the audio only has to say *where*
the boundaries are:

    verse (pass A, natural tempo)
      line   x N          -> N-1 internal pauses
        phrase x 2        -> 1 pause, at the metrical caesura
          word x k        -> k-1 pauses

Every split is count-constrained and scored against syllable-weighted
expectations, so a deep-but-wrong pause cannot win. Each split reports a
confidence, and low-confidence verses are meant to be fixed in the Tag editor
rather than trusted blindly.

    python3 auto_split.py --eval             score against the hand-tagged files
    python3 auto_split.py --all [limit]      write auto_data.json for every mp3
"""
import json, os, re, sys
from itertools import combinations
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gapdetect import decode, stft_mag, smooth, SR, HOP, NFFT
from sandhi_map import build as sandhi_build

FPS = 100.0
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
BRAJA = os.path.join(REPO, "BrajaBeats_Gita_MP3")
VOWELS = re.compile(r"(ai|au|[aāiīuūṛṝḷeo])")


def syllables(w):
    return max(1, len(VOWELS.findall(w.lower())))


def vocal_db(y):
    S = stft_mag(y)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (f >= 300) & (f <= 3500)
    floor = np.percentile(S, 15, axis=0, keepdims=True)
    resid = np.maximum(S - floor, 1e-8)
    return 20 * np.log10(np.sqrt((resid[:, band] ** 2).mean(axis=1)) + 1e-8)


def dips(x, min_w=0.05, edge=0.15):
    """Every plausible low-energy run in x, as (start, end, depth) frames."""
    out = {}
    n = len(x)
    for pct in (20, 25, 30, 35, 40, 45, 50, 55):
        thr = np.percentile(x, pct)
        d = np.diff((x < thr).astype(np.int8), prepend=0, append=0)
        runs = list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))
        merged = []
        for a, b in runs:
            if merged and (a - merged[-1][1]) / FPS < 0.10:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        for a, b in merged:
            if (b - a) / FPS < min_w or a / FPS < edge or b / FPS > n / FPS - edge:
                continue
            key = (round(a / 5), round(b / 5))
            dep = float((thr - x[a:b]).sum())
            if dep > out.get(key, (0, 0, 0))[2]:
                out[key] = (a, b, dep)
    return sorted(out.values())


def split_region(db, t0, t1, weights, min_w=0.05, max_dips=14):
    """Cut [t0,t1] into len(weights) spans. Chooses the combination of dips whose
    cut points best match the syllable-weighted expectation.
    Returns (spans, score) where lower score = better fit; inf if impossible."""
    k = len(weights)
    if k == 1:
        return [(t0, t1)], 0.0
    i, j = int(t0 * FPS), int(t1 * FPS)
    x = smooth(db[i:j], 7)
    n = len(x)
    if n < 12:
        return None, float("inf")

    w = np.asarray(weights, dtype=float)
    expected = np.cumsum(w)[:-1] / w.sum()

    cand = dips(x, min_w=min_w)
    if len(cand) < k - 1:
        return None, float("inf")
    # keep the deepest handful so the combinatorics stay small
    cand = sorted(sorted(cand, key=lambda d: -d[2])[:max_dips])
    maxdep = max(d[2] for d in cand) or 1.0

    best, combo_best = float("inf"), None
    for combo in combinations(range(len(cand)), k - 1):
        cuts = np.array([(cand[c][0] + cand[c][1]) / 2 / n for c in combo])
        if np.any(np.diff(cuts) <= 0):
            continue
        shape = float(np.abs(cuts - expected).mean())
        depth = float(np.mean([cand[c][2] for c in combo])) / maxdep
        score = shape - 0.12 * depth
        if score < best:
            best, combo_best = score, combo
    if combo_best is None:
        return None, float("inf")

    gaps = sorted((cand[c][0], cand[c][1]) for c in combo_best)
    bounds = [0] + [g for gp in gaps for g in gp] + [n]
    spans = [(t0 + bounds[m] / FPS, t0 + bounds[m + 1] / FPS)
             for m in range(0, len(bounds) - 1, 2)]
    if any(b - a <= 0.10 for a, b in spans):
        return None, float("inf")
    return spans, best


def voiced_extent(db, lo=0.0, hi=None):
    """First and last frame with real energy, so we don't start mid-silence."""
    x = smooth(db, 11)
    thr = np.percentile(x, 45)
    on = np.flatnonzero(x > thr)
    if not len(on):
        return 0.0, len(x) / FPS
    return on[0] / FPS, on[-1] / FPS


def find_passA(db, dur, lines):
    """Pass A is the first, faster recitation. Rather than hunting for the seam
    directly (pass-A and pass-B pauses overlap in length), try every plausible
    end point and keep the one whose N-line split fits the text best."""
    w = [sum(syllables(t) for t in ln.split()) for ln in lines]
    t_on, _ = voiced_extent(db)
    best = (float("inf"), None, None)
    for frac in np.arange(0.24, 0.62, 0.01):
        end = dur * frac
        if end - t_on < 2.0:
            continue
        spans, score = split_region(db, t_on, end, w, min_w=0.12)
        if spans is None:
            continue
        # a good seam also leaves the last line ending near `end`
        if score < best[0]:
            best = (score, spans, end)
    return best[1], best[0], best[2]


def analyse(audio_path, verse):
    lines, tokens, tok_line, syns, path, _c = sandhi_build(verse)
    meaning = {}
    for si, ti, _r, _f in path:
        key = " + ".join(syns[k] for k in si)
        mean = " / ".join(verse["synonyms"][syns[k]]["meaning"] for k in si)
        for t in ti:
            meaning[t] = (key, mean)

    y = decode(audio_path)
    dur = len(y) / SR
    db = vocal_db(y)

    line_spans, line_score, passA_end = find_passA(db, dur, lines)
    if line_spans is None:
        return None

    out_lines, conf = [], [line_score]
    ti0 = 0
    for li, ln in enumerate(lines):
        toks = ln.split()
        a, b = line_spans[li]
        rec = {"index": li, "text": ln,
               "line_audio": {"start": round(a, 3), "end": round(b, 3)},
               "chunks": []}

        # phrase split: 2 phrases at the metrical caesura, by syllable weight
        if len(toks) >= 2:
            mid = caesura(toks)
            groups = [toks[:mid], toks[mid:]]
        else:
            groups = [toks]
        gw = [sum(syllables(t) for t in g) for g in groups]
        pspans, pscore = (split_region(db, a, b, gw, min_w=0.05)
                          if len(groups) > 1 else ([(a, b)], 0.0))
        if pspans is None:
            pspans, pscore = proportional(a, b, gw), 0.5
        conf.append(pscore)

        for gi, grp in enumerate(groups):
            pa, pb = pspans[gi]
            wspans, wscore = (split_region(db, pa, pb, [syllables(t) for t in grp],
                                           min_w=0.04)
                              if len(grp) > 1 else ([(pa, pb)], 0.0))
            if wspans is None:
                wspans, wscore = proportional(pa, pb, [syllables(t) for t in grp]), 0.5
            conf.append(wscore)
            chunk = {"text": " ".join(grp),
                     "chunk_audio": {"start": round(pa, 3), "end": round(pb, 3)},
                     "split_method": "auto", "words": []}
            for wi, tk in enumerate(grp):
                ws, we = wspans[wi]
                key, mean = meaning.get(ti0 + wi, ("", ""))
                chunk["words"].append({
                    "token": tk, "synonym": key, "meaning": mean,
                    "word_audio": {"start": round(ws, 3), "end": round(we, 3)},
                    "exact": False})
            ti0 += len(grp)
            rec["chunks"].append(chunk)
        out_lines.append(rec)

    score = float(np.mean([c for c in conf if np.isfinite(c)]))
    return {"lines": out_lines, "passA_end": round(passA_end, 3),
            "confidence": round(min(1.0, max(0.0, 1.0 - score * 4)), 3),
            "verse_audio": {"start": round(line_spans[0][0], 3),
                            "end": round(line_spans[-1][1], 3)}}


def caesura(toks):
    """Split point closest to half the line's syllables."""
    syl = [syllables(t) for t in toks]
    tot, run, best, bi = sum(syl), 0, 1e9, 1
    for i in range(1, len(toks)):
        run += syl[i - 1]
        d = abs(run - tot / 2)
        if d < best:
            best, bi = d, i
    return bi


def proportional(a, b, weights):
    w = np.asarray(weights, dtype=float)
    e = a + (b - a) * np.concatenate([[0], np.cumsum(w) / w.sum()])
    return [(e[i], e[i + 1]) for i in range(len(weights))]


# ---------------- evaluation ----------------
def evaluate():
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    cases = [("1", "14", "tagged_gita_1_14.json", "Bhagavad-gita 1.14.mp3"),
             ("18", "66", "tagged_gita_18_66.json", "Bhagavad-gita 18.66.mp3")]
    for ch, sh, tag, mp3 in cases:
        verse = next(v for v in gita if v["chapter"] == ch and v["shloka"] == sh)
        res = analyse(os.path.join(BRAJA, mp3), verse)
        gt = json.load(open(os.path.join(REPO, tag)))["segments"]
        lines = [ln.strip() for ln in verse["english"].split("\n") if ln.strip()]
        gtl = sorted((s["start"]/1000, s["end"]/1000) for s in gt
                     if s["label"].strip() in lines)
        print(f"\n=== BG {ch}.{sh}   confidence {res['confidence']}"
              f"   passA_end {res['passA_end']}s ===")
        errs = []
        for i, L in enumerate(res["lines"]):
            a, b = L["line_audio"]["start"], L["line_audio"]["end"]
            if i < len(gtl):
                ga, gb = gtl[i]
                es, ee = abs(a-ga)*1000, abs(b-gb)*1000
                errs += [es, ee]
                print(f"  L{i} auto {a:6.2f}-{b:6.2f}   hand {ga:6.2f}-{gb:6.2f}"
                      f"   err {es:5.0f}/{ee:5.0f} ms   {L['text']}")
        if errs:
            print(f"  line boundary error: median {np.median(errs):.0f} ms  "
                  f"mean {np.mean(errs):.0f} ms  max {np.max(errs):.0f} ms")
        nw = sum(len(c["words"]) for L in res["lines"] for c in L["chunks"])
        print(f"  produced {len(res['lines'])} lines, "
              f"{sum(len(L['chunks']) for L in res['lines'])} phrases, {nw} words")


def run_all(limit=None):
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    index = {f"{v['chapter']}.{v['shloka']}": v for v in gita}
    files = sorted(f for f in os.listdir(BRAJA) if f.lower().endswith(".mp3"))
    out, skipped = [], []
    for n, fn in enumerate(files):
        if limit and len(out) >= limit:
            break
        m = re.search(r"(\d+)\.(\d+)", fn)
        if not m:
            skipped.append((fn, "no chapter.verse in filename")); continue
        vid = f"{m.group(1)}.{m.group(2)}"
        verse = index.get(vid)
        if verse is None:
            skipped.append((fn, f"{vid} not in gita.json")); continue
        try:
            res = analyse(os.path.join(BRAJA, fn), verse)
        except Exception as exc:
            skipped.append((fn, f"error: {exc}")); continue
        if res is None:
            skipped.append((fn, "no usable split")); continue
        out.append({"id": vid, "chapter": m.group(1), "shloka": m.group(2),
                    "audio": "braja/" + fn, "source_file": fn,
                    "sanskrit": verse.get("sanskrit", ""),
                    "translation": verse.get("translation", ""),
                    "align_cost": 0.0, "auto": True,
                    "confidence": res["confidence"],
                    "verse_audio": res["verse_audio"], "lines": res["lines"],
                    "synonyms": [{"key": k, "meaning": v["meaning"]}
                                 for k, v in verse["synonyms"].items()]})
        if (n + 1) % 25 == 0:
            print(f"  … {n+1}/{len(files)}", flush=True)

    out.sort(key=lambda v: (int(v["chapter"]), int(v["shloka"])))
    with open(os.path.join(ROOT, "auto_data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    cs = [v["confidence"] for v in out]
    print(f"\nwrote auto_data.json: {len(out)} verses, {len(skipped)} skipped")
    if cs:
        cs = np.array(cs)
        for t in (0.8, 0.6, 0.4):
            print(f"  confidence >= {t}: {(cs >= t).sum()} ({(cs >= t).mean()*100:.0f}%)")
        print(f"  median confidence {np.median(cs):.2f}")
    for fn, why in skipped[:10]:
        print(f"  skipped {fn}: {why}")


if __name__ == "__main__":
    if "--eval" in sys.argv:
        evaluate()
    elif "--all" in sys.argv:
        i = sys.argv.index("--all")
        lim = int(sys.argv[i+1]) if len(sys.argv) > i+1 else None
        run_all(lim)
    else:
        print(__doc__)
