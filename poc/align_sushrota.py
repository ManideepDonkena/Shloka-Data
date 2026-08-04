"""CTC forced alignment using Sushrota, a Sanskrit-native Conformer.

`prathoshap/sushrota-sanskrit-asr` is an IndicConformer fine-tuned on Sanskrit
recitation (CER 3.6-7.3%). It ships only as a .nemo, and stock NeMo cannot load
it: the RNNT branch uses a `multisoftmax` argument from AI4Bharat's fork, and the
tokenizer config is typed `multilingual` where NeMo expects `agg`.

We do not need RNNT. Forced alignment only needs
    mel preprocessor -> ConformerEncoder -> ctc_decoder (1x1 conv)
and all three are stock NeMo modules, so we build them straight from the config
and load just those weights.

The CTC head covers all 22 IndicConformer languages (5632 classes + blank) with
Sanskrit occupying a 256-token slice. The offset is verified against the
Sanskrit tokenizer's own vocabulary rather than assumed.

    .venv-nemo/bin/python align_sushrota.py --probe
    .venv-nemo/bin/python align_sushrota.py --eval
    .venv-nemo/bin/python align_sushrota.py --all [limit]
"""
import json, os, re, sys, tarfile
import numpy as np
import torch
import torchaudio.functional as AF
from omegaconf import OmegaConf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gapdetect import decode
from sandhi_map import build as sandhi_build

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
BRAJA = os.path.join(REPO, "BrajaBeats_Gita_MP3")
WORK = os.path.join(ROOT, ".sushrota")
SR = 16000
HF_REPO = "prathoshap/sushrota-sanskrit-asr"
NEMO_FILE = "sushrota_sanskrit_asr_v5.nemo"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

_state = None


# ---------------- model ----------------
def unpack():
    """Extract the .nemo once into .sushrota/."""
    cfg_p = os.path.join(WORK, "model_config.yaml")
    if os.path.exists(cfg_p):
        return WORK
    from huggingface_hub import hf_hub_download
    nemo = hf_hub_download(HF_REPO, NEMO_FILE)
    os.makedirs(WORK, exist_ok=True)
    with tarfile.open(nemo) as t:
        t.extractall(WORK)
    return WORK


def build():
    """preprocessor + encoder + CTC head, with the Sanskrit token offset."""
    global _state
    if _state is not None:
        return _state
    import nemo.collections.asr as nemo_asr
    import sentencepiece as spm

    d = unpack()
    cfg = OmegaConf.load(os.path.join(d, "model_config.yaml"))

    import inspect

    def mk(node, cls):
        """Instantiate, dropping arguments only AI4Bharat's fork understands."""
        kw = OmegaConf.to_container(node, resolve=True)
        kw.pop("_target_", None)
        allowed = set(inspect.signature(cls.__init__).parameters)
        dropped = [k for k in kw if k not in allowed]
        for k in dropped:
            kw.pop(k)
        if dropped:
            print(f"  note: {cls.__name__} ignoring fork-only args {dropped}")
        return cls(**kw)

    prep = mk(cfg.preprocessor, nemo_asr.modules.AudioToMelSpectrogramPreprocessor)
    enc = mk(cfg.encoder, nemo_asr.modules.ConformerEncoder)
    dec = mk(cfg.aux_ctc.decoder, nemo_asr.modules.ConvASRDecoder)

    sd = torch.load(os.path.join(d, "model_weights.ckpt"),
                    map_location="cpu", weights_only=True)
    take = lambda p: {k[len(p) + 1:]: v for k, v in sd.items() if k.startswith(p + ".")}
    prep.load_state_dict(take("preprocessor"), strict=False)
    missing = enc.load_state_dict(take("encoder"), strict=False)
    assert not missing.missing_keys, f"encoder missing {missing.missing_keys[:4]}"
    dec.load_state_dict(take("ctc_decoder"), strict=True)

    for m in (prep, enc, dec):
        m.to(DEVICE).eval()

    # Sanskrit tokenizer, and where its tokens sit in the shared CTC vocabulary
    sa = cfg.tokenizer.langs["sa"]
    model_path = os.path.join(d, str(sa.model_path).replace("nemo:", ""))
    sp = spm.SentencePieceProcessor(model_file=model_path)
    vocab = list(cfg.aux_ctc.decoder.vocabulary)
    offset = find_offset(sp, vocab)

    n_sa = sp.get_piece_size()
    blank = len(vocab)                                   # 5632
    keep = torch.tensor(list(range(offset, offset + n_sa)) + [blank])
    _state = dict(prep=prep, enc=enc, dec=dec, sp=sp, offset=offset,
                  n_classes=len(vocab), n_sa=n_sa, keep=keep, blank_local=n_sa)
    return _state


def find_offset(sp, vocab):
    """Locate the Sanskrit slice by matching the tokenizer's own pieces."""
    probe = [sp.id_to_piece(i) for i in range(5, 40)]
    size = sp.get_piece_size()
    for off in range(0, len(vocab) - size + 1, 256):
        window = vocab[off:off + size]
        hits = sum(1 for p in probe if p in window)
        if hits >= len(probe) * 0.9:
            return off
    raise RuntimeError("could not locate the Sanskrit token slice")


def log_probs(y):
    """Log-probs over [Sanskrit slice + blank] only.

    The CTC head is shared across 22 languages and was trained with a
    per-language softmax, so normalising over all 5632 classes would misweight
    blank against the Sanskrit tokens. Take raw logits and softmax over just
    this language's slice plus blank, which is what the head was trained to do.
    """
    st = build()
    wav = torch.from_numpy(y.copy()).unsqueeze(0).to(DEVICE)
    ln = torch.tensor([wav.shape[1]], device=DEVICE)
    with torch.inference_mode():
        feats, flen = st["prep"](input_signal=wav, length=ln)
        emb, _ = st["enc"](audio_signal=feats, length=flen)
        logits = st["dec"].decoder_layers(emb)           # (1, C, T), pre-softmax
        logits = logits.transpose(1, 2)[0]               # (T, C)
        keep = st["keep"].to(logits.device)
        lp = torch.log_softmax(logits.index_select(1, keep).float(), dim=-1)
    return lp.cpu(), float(len(y) / SR) / lp.shape[0]


# ---------------- alignment ----------------
def to_deva(word):
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate as tr
    w = re.sub(r"[’ʼ'`]", "", word).replace("-", "")
    return tr(w, sanscript.IAST, sanscript.DEVANAGARI)


def align(audio_path, words, crop=None):
    """crop: align only the first `crop` fraction of the file.

    MMS has a `*` star token to absorb the second pass. Sushrota has no such
    token, so with the whole file in view the aligner is free to match a word
    against its repeat in the word-by-word pass -- BG 1.14's last word landed at
    50.9 s. Cropping is the equivalent guard; `align_best` picks the crop.
    """
    st = build()
    y = decode(audio_path, sr=SR)
    if crop:
        y = y[: int(len(y) * crop)]
    lp, sec_per_frame = log_probs(y)

    ids, owner = [], []
    for i, w in enumerate(words):
        pieces = st["sp"].encode(to_deva(w), out_type=int)
        pieces = [p for p in pieces if p != 0]           # drop <unk>
        for p in pieces:
            ids.append(p)                                # local index in the slice
            owner.append(i)
    if not ids:
        return None

    targets = torch.tensor([ids], dtype=torch.int32)
    lpb = lp.unsqueeze(0)
    try:
        labels, scores = AF.forced_align(lpb, targets, blank=st["blank_local"])
    except Exception:
        return None
    labels, scores = labels[0], scores[0].exp()

    # collapse the frame path into one span per target token, then per word
    spans = {}
    k = -1
    prev = None
    for f, lab in enumerate(labels.tolist()):
        if lab == st["blank_local"]:
            prev = None
            continue
        if lab != prev:
            k += 1
            prev = lab
        if k >= len(owner):
            break
        w = owner[k]
        s = spans.setdefault(w, [f, f, []])
        s[1] = f
        s[2].append(float(scores[f]))

    out = []
    for i in range(len(words)):
        if i not in spans:
            out.append(None)
            continue
        a, b, sc = spans[i]
        out.append((a * sec_per_frame, (b + 1) * sec_per_frame, float(np.mean(sc))))
    for i, v in enumerate(out):
        if v is None:
            prev = out[i - 1] if i else None
            out[i] = (prev[1], prev[1] + 0.05, 0.0) if prev else (0.0, 0.05, 0.0)
    return out


def align_best(audio_path, words, crops=(0.32, 0.38, 0.44, 0.50, 0.58, 1.0)):
    """Try several crops, keep the one the model is most confident about.
    A crop that splits a word mid-utterance scores badly, so this settles on the
    first pass without needing to detect the seam directly."""
    best = (None, -1.0, None)
    for c in crops:
        spans = align(audio_path, words, crop=c)
        if spans is None:
            continue
        sc = float(np.mean([s for _, _, s in spans]))
        # a sane result also keeps every word plausibly short
        longest = max(b - a for a, b, _ in spans)
        if longest > 8.0:
            sc -= 0.5
        if sc > best[1]:
            best = (spans, sc, c)
    return best


# ---------------- modes ----------------
def _verse(gita, ch, sh):
    return next(v for v in gita if v["chapter"] == ch and v["shloka"] == sh)


def probe():
    st = build()
    print(f"device            {DEVICE}")
    print(f"ctc classes       {st['n_classes']} (+blank)")
    print(f"sanskrit slice    offset {st['offset']}, size {st['sp'].get_piece_size()}")
    for w in ["tataḥ", "śvetair", "mokṣayiṣyāmi", "dharma-kṣetre"]:
        d = to_deva(w)
        print(f"  {w:16s} -> {d:16s} -> {st['sp'].encode(d, out_type=str)}")


def evaluate():
    from align_mms import snap_boundaries, vocal_env
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    for ch, sh, tag, mp3 in [("1", "14", "tagged_gita_1_14.json", "Bhagavad-gita 1.14.mp3"),
                             ("18", "66", "tagged_gita_18_66.json", "Bhagavad-gita 18.66.mp3")]:
        verse = _verse(gita, ch, sh)
        lines, tokens, tok_line, *_ = sandhi_build(verse)
        path = os.path.join(BRAJA, mp3)
        spans, _sc, crop = align_best(path, tokens)
        if spans is None:
            print(f"BG {ch}.{sh}: alignment failed")
            continue
        env = vocal_env(decode(path, sr=SR))
        snapped = snap_boundaries([(a, b) for a, b, _ in spans], env)
        sc = [s for _, _, s in spans]

        gt = sorted((s["start"]/1000, s["end"]/1000) for s in
                    json.load(open(os.path.join(REPO, tag)))["segments"]
                    if s["label"].strip() in lines)
        print(f"\n=== BG {ch}.{sh} (sushrota)  mean score {np.mean(sc):.3f}  crop {crop} ===")
        errs, i0 = [], 0
        for li, ln in enumerate(lines):
            n = len(ln.split())
            a, b = snapped[i0][0], snapped[i0 + n - 1][1]
            i0 += n
            if li < len(gt):
                ga, gb = gt[li]
                es, ee = abs(a-ga)*1000, abs(b-gb)*1000
                errs += [es, ee]
                print(f"  L{li} {a:6.2f}-{b:6.2f}  hand {ga:6.2f}-{gb:6.2f}"
                      f"   err {es:5.0f}/{ee:5.0f} ms   {ln}")
        if errs:
            print(f"  line boundary error: median {np.median(errs):.0f} ms  "
                  f"mean {np.mean(errs):.0f} ms  max {np.max(errs):.0f} ms")


def caesura(toks):
    from align_mms import caesura as c
    return c(toks)


def analyse(audio_path, verse):
    from align_mms import snap_boundaries, vocal_env
    lines, tokens, tok_line, syns, path, _c = sandhi_build(verse)
    meaning = {}
    for si, ti, _r, _f in path:
        key = " + ".join(syns[k] for k in si)
        mean = " / ".join(verse["synonyms"][syns[k]]["meaning"] for k in si)
        for t in ti:
            meaning[t] = (key, mean)

    spans, _sc, _crop = align_best(audio_path, tokens)
    if spans is None:
        return None
    env = vocal_env(decode(audio_path, sr=SR))
    snapped = snap_boundaries([(a, b) for a, b, _ in spans], env)
    spans = [(a, b, s) for (a, b), (_, _, s) in zip(snapped, spans)]

    out_lines, scores, ti0 = [], [], 0
    for li, ln in enumerate(lines):
        toks = ln.split()
        idx = list(range(ti0, ti0 + len(toks)))
        rec = {"index": li, "text": ln,
               "line_audio": {"start": round(spans[idx[0]][0], 3),
                              "end": round(spans[idx[-1]][1], 3)},
               "chunks": []}
        groups = ([toks[:caesura(toks)], toks[caesura(toks):]]
                  if len(toks) >= 2 else [toks])
        g0 = 0
        for grp in groups:
            gidx = idx[g0:g0 + len(grp)]
            chunk = {"text": " ".join(grp),
                     "chunk_audio": {"start": round(spans[gidx[0]][0], 3),
                                     "end": round(spans[gidx[-1]][1], 3)},
                     "split_method": "sushrota", "words": []}
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
            skipped.append(fn); continue
        vid = f"{m.group(1)}.{m.group(2)}"
        verse = index.get(vid)
        if verse is None:
            skipped.append(fn); continue
        try:
            res = analyse(os.path.join(BRAJA, fn), verse)
        except Exception as exc:
            skipped.append(f"{fn}: {exc}"); continue
        if res is None:
            skipped.append(fn); continue
        out.append({"id": vid, "chapter": m.group(1), "shloka": m.group(2),
                    "audio": "braja/" + fn, "source_file": fn,
                    "sanskrit": verse.get("sanskrit", ""),
                    "translation": verse.get("translation", ""),
                    "align_cost": 0.0, "auto": True, "aligner": "sushrota",
                    "confidence": res["confidence"],
                    "verse_audio": res["verse_audio"], "lines": res["lines"],
                    "synonyms": [{"key": k, "meaning": v["meaning"]}
                                 for k, v in verse["synonyms"].items()]})
        if (n + 1) % 20 == 0:
            print(f"  … {n+1}/{len(files)}", flush=True)

    out.sort(key=lambda v: (int(v["chapter"]), int(v["shloka"])))
    with open(os.path.join(ROOT, "sushrota_data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote sushrota_data.json: {len(out)} verses, {len(skipped)} skipped")
    if out:
        c = np.array([v["confidence"] for v in out])
        print(f"  confidence median {np.median(c):.2f}  min {c.min():.2f}  "
              f">=0.6: {(c>=0.6).mean()*100:.0f}%")


if __name__ == "__main__":
    a = sys.argv
    if "--probe" in a:
        probe()
    elif "--eval" in a:
        evaluate()
    elif "--all" in a:
        i = a.index("--all")
        run_all(int(a[i+1]) if len(a) > i+1 and a[i+1].isdigit() else None)
    else:
        print(__doc__)
