"""Per-verse: concat Vagdhenu half-verse wavs (known gap), MMS-align IAST words, join synonyms.
Writes out/verses/<c.v>.wav + <c.v>.json  {halves:[{start,end}], words:[{iast,start,end,half,synonym,meaning}]}"""
import json, os, re, sys, glob, unicodedata
import numpy as np, soundfile as sf, torch, torchaudio
sys.path.insert(0, "/home/mani/shloka/Shloka-Data/poc")
from align_mms import romanize
SR = 24000; GAP = 0.55
mapping = {m["id"]: m for m in json.load(open("/home/mani/shloka/Shloka-Data/poc/mapping.json"))}
bundle = torchaudio.pipelines.MMS_FA; dev = "cuda" if torch.cuda.is_available() else "cpu"
model = bundle.get_model().eval().to(dev); tok = bundle.get_tokenizer(); aligner = bundle.get_aligner()
os.makedirs("out/verses", exist_ok=True)

ids = sorted({re.match(r"(.+)_p\d+$", os.path.basename(f)[:-4]).group(1) for f in glob.glob("out/padas/*.wav")})
for vid in ids:
    parts = sorted(glob.glob(f"out/padas/{vid}_p*.wav"), key=lambda f: int(re.search(r"_p(\d+)", f).group(1)))
    wav, halves, t = [], [], 0.0
    for i, p in enumerate(parts):
        a, sr = sf.read(p); assert sr == SR
        if i: wav.append(np.zeros(int(GAP * SR))); t += GAP
        halves.append({"start": round(t, 3), "end": round(t + len(a) / SR, 3)}); wav.append(a); t += len(a) / SR
    audio = np.concatenate(wav); sf.write(f"out/verses/{vid}.wav", audio, SR)
    # words: flatten mapping tokens, skip speaker lines
    toks = []
    for ln in mapping[vid]["lines"]:
        if ln["text"].strip().endswith("uvāca"): continue
        toks += ln["tokens"]
    words = [romanize(t["token"]) for t in toks]
    keep = [i for i, w in enumerate(words) if w]
    w16 = torchaudio.functional.resample(torch.tensor(audio, dtype=torch.float32)[None], SR, 16000).to(dev)
    with torch.inference_mode():
        em, _ = model(w16)
        spans = aligner(em[0], tok([words[i] for i in keep]))
    ratio = w16.shape[1] / em.shape[1] / 16000
    out = []
    for i, sp in zip(keep, spans):
        s, e = sp[0].start * ratio, sp[-1].end * ratio
        h = next((k for k, hv in enumerate(halves) if s < hv["end"] + GAP / 2), len(halves) - 1)
        out.append({"iast": toks[i]["token"], "start": round(s, 3), "end": round(e, 3), "half": h,
                    "synonym": toks[i].get("synonym"), "meaning": toks[i].get("meaning")})
    json.dump({"id": vid, "dur": round(len(audio) / SR, 3), "halves": halves, "words": out,
               "translation": mapping[vid]["translation"]}, open(f"out/verses/{vid}.json", "w"), ensure_ascii=False, indent=1)
    print(vid, f"{len(audio)/SR:.1f}s", len(out), "words")
