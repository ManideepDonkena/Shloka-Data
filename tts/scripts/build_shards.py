"""gita.json -> per-pada Vagdhenu render shards.

One clip per pada (not per verse) so pada boundaries are exact by construction:
we concatenate the pada wavs ourselves with a known gap and record the timings.
Usage: build_shards.py GITA_JSON OUT_SHARD [--verses 2.20,18.66 | --all]
"""
import json, re, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("gita"); ap.add_argument("out")
ap.add_argument("--verses", default="")
ap.add_argument("--wavdir", default="out/padas")
a = ap.parse_args()

def padas(sk):
    """Devanagari verse lines -> list of pada strings (drops 'X उवाच' speaker lines, danda marks, verse no.)."""
    lines = [l.strip() for l in sk.split("\n") if l.strip()]
    lines = [l for l in lines if not re.search(r"उवाच\s*$", l)]
    out = []
    for l in lines:
        l = re.sub(r"॥.*?॥", "", l)             # verse number
        l = l.replace("-", "").replace(":", "ः").replace("।", "|")
        for half in l.split("|"):
            half = re.sub(r"[ऽ]", "ऽ", half).strip()
            if half: out.append(half)
    return out

g = json.load(open(a.gita))
want = set(a.verses.split(",")) if a.verses else None
shard = []
for e in g:
    if "-" in e["shloka"]: continue               # merged verses handled later
    vid = f'{e["chapter"]}.{e["shloka"]}'
    if want and vid not in want: continue
    ps = padas(e["sanskrit"])
    for i, p in enumerate(ps):
        shard.append({"id": f"{vid}_p{i}", "meter": "anushtubh", "padas": [p], "seed": 60,
                      "no_sandhi": True, "out": f"{a.wavdir}/{vid}_p{i}.wav"})
json.dump(shard, open(a.out, "w"), ensure_ascii=False, indent=1)
print(len(shard), "clips")
