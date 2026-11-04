"""Per-verse: concat Vagdhenu half-verse wavs (known gap), MMS-align the words, and write
poc/data.json-schema entries (verse_audio / lines / chunks / words with word_audio) so the existing
Shloka-Data app, with its highlighting, can play them as a "TTS" source.
Usage: assemble_align.py PAD_DIR OUT_DIR   ->  OUT_DIR/<id>.wav, OUT_DIR/tts_data.json"""
import json, os, re, sys, glob
import numpy as np, soundfile as sf, torch, torchaudio
POC = os.environ.get("POC", "/home/mani/shloka/Shloka-Data/poc"); sys.path.insert(0, POC)
from align_mms import romanize
PADS, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
SR = 24000; GAP = 0.55
mapping = {m["id"]: m for m in json.load(open(f"{POC}/mapping.json"))}
bundle = torchaudio.pipelines.MMS_FA; dev = "cuda" if torch.cuda.is_available() else "cpu"
model = bundle.get_model().eval().to(dev); tok = bundle.get_tokenizer(); aligner = bundle.get_aligner()
CONS = "kgṅcjñṭḍṇtdnpbmyrlvśṣsh"

def rend_words(deva):  # rendered (post hyphen-strip) half text -> words
    return deva.split()

ids = sorted({re.match(r"(.+)_p\d+$", os.path.basename(f)[:-4]).group(1) for f in glob.glob(f"{PADS}/*.wav")})
res = []
for vid in ids:
    parts = sorted(glob.glob(f"{PADS}/{vid}_p*.wav"), key=lambda f: int(re.search(r"_p(\d+)", f).group(1)))
    wav, halves, t = [], [], 0.0
    for i, p in enumerate(parts):
        a, sr = sf.read(p); assert sr == SR
        if i: wav.append(np.zeros(int(GAP * SR))); t += GAP
        halves.append((t, t + len(a) / SR)); wav.append(a); t += len(a) / SR
    audio = np.concatenate(wav); sf.write(f"{OUT}/{vid}.wav", audio, SR)
    m = mapping[vid]
    toks, line_of = [], []
    for li, ln in enumerate(l for l in m["lines"] if not l["text"].strip().endswith("uvāca")):
        for tk in ln["tokens"]: toks.append(tk); line_of.append(li)
    texts = [romanize(tk["token"]) for tk in toks]
    # cross-line sandhi: the source marks a word split across a half-verse break with "-"
    # (kadāci- / nnāyaṁ). Rendered audio says "kadāci" + "nnāyaṁ", so move the final consonant
    # of the last token before the break onto the front of the first token after it.
    dl = [l.strip() for l in m["sanskrit"].split("\n") if l.strip() and not l.strip().endswith("उवाच")]
    for h, l in enumerate(dl[:-1]):
        if l.rstrip(" ।॥").endswith("-"):
            prev = max(i for i, x in enumerate(line_of) if x // 2 == h); nxt = min(i for i, x in enumerate(line_of) if x // 2 == h + 1)
            c = texts[prev][-1]
            if texts[nxt].startswith(c) and not texts[prev][-1] in "aeiou":
                texts[prev] = texts[prev][:-1]; texts[nxt] = c + texts[nxt]
    keep = [i for i, w in enumerate(texts) if w]
    w16 = torchaudio.functional.resample(torch.tensor(audio, dtype=torch.float32)[None], SR, 16000).to(dev)
    with torch.inference_mode():
        em, _ = model(w16); spans = aligner(em[0], tok([texts[i] for i in keep]))
    ratio = w16.shape[1] / em.shape[1] / 16000
    W = {}
    for i, sp in zip(keep, spans):
        W[i] = {"start": round(sp[0].start * ratio, 3), "end": round(sp[-1].end * ratio, 3),
                "score": round(float(np.mean([s.score for s in sp])), 3)}
    lines, synonyms, seen = [], [], set()
    for li in range(max(line_of) + 1):
        idx = [i for i in range(len(toks)) if line_of[i] == li and i in W]
        words = []
        for i in idx:
            tk = toks[i]
            words.append({"token": tk["token"], "synonym": tk.get("synonym"), "meaning": tk.get("meaning"),
                          "word_audio": {"start": W[i]["start"], "end": W[i]["end"]}, "score": W[i]["score"],
                          "exact": True, "suspect": W[i]["score"] < 0.5 or (W[i]["end"] - W[i]["start"]) < 0.06})
            if tk.get("synonym") and tk["synonym"] not in seen:
                seen.add(tk["synonym"]); synonyms.append({"key": tk["synonym"], "meaning": tk.get("meaning")})
        if not words: continue
        la = {"start": words[0]["word_audio"]["start"], "end": words[-1]["word_audio"]["end"]}
        lines.append({"index": li, "text": " ".join(w["token"] for w in words), "line_audio": la,
                      "chunks": [{"text": " ".join(w["token"] for w in words), "chunk_audio": la,
                                  "split_method": "tts", "words": words}]})
    allw = [w for l in lines for c in l["chunks"] for w in c["words"]]
    res.append({"id": vid, "chapter": m["chapter"], "shloka": m["shloka"], "audio": f"audio-tts/{vid}.wav",
                "sanskrit": m["sanskrit"], "translation": m["translation"], "auto": True, "aligner": "tts-mms",
                "confidence": round(float(np.mean([w["score"] for w in allw])), 3),
                "suspect_words": sum(w["suspect"] for w in allw),
                "verse_audio": {"start": 0, "end": round(len(audio) / SR, 3)}, "lines": lines, "synonyms": synonyms})
    print(vid, f"{len(audio)/SR:.1f}s conf={res[-1]['confidence']} suspect={res[-1]['suspect_words']}",
          [(w["token"], w["score"]) for w in allw if w["suspect"]])
json.dump(res, open(f"{OUT}/tts_data.json", "w"), ensure_ascii=False)
