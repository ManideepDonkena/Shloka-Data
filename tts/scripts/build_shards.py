"""gita.json -> per-half-verse Vagdhenu render shards (one clip per half, so boundaries are exact).

A half-verse ends at a danda (। or ॥); 4-line tristubh verses are joined back into 2 halves.
Meter is picked from the half's syllable count: 16 -> anushtubh, 22-23 -> upajati, 24 -> vamsastha,
anything else -> anushtubh (the renderer re-splits long text itself).
Usage: build_shards.py GITA_JSON OUT_SHARD [--verses 2.20,18.66 | --all] [--wavdir out/padas] [--split N]
"""
import json, re, argparse

ap = argparse.ArgumentParser()
ap.add_argument("gita"); ap.add_argument("out")
ap.add_argument("--verses", default=""); ap.add_argument("--all", action="store_true")
ap.add_argument("--wavdir", default="out/padas")
ap.add_argument("--split", type=int, default=1, help="write OUT.0 .. OUT.N-1 (verses dealt round-robin)")
a = ap.parse_args()

def n_akshara(s):
    n = 0
    for i, c in enumerate(s):
        o = ord(c)
        if 0x0905 <= o <= 0x0914: n += 1
        elif 0x0915 <= o <= 0x0939 and (s[i + 1] if i + 1 < len(s) else "") != "्": n += 1
    return n

def meter_for(n):
    return "anuṣṭubh" if n in (15, 16, 17) else "upajāti" if n in (21, 22, 23) else "vaṃśastha" if n == 24 else "anuṣṭubh"

def halves(sk):
    lines = [l.strip() for l in sk.split("\n") if l.strip()]
    lines = [l for l in lines if not re.search(r"वाच\s*$", l)]
    out, cur = [], []
    for l in lines:
        cur.append(l)
        if re.search(r"[।॥|]", l): out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    res = []
    for h in out:
        h = re.sub(r"॥.*?॥", "", h)                       # verse number
        h = re.sub("[‌‍]", "", h).replace("-", "").replace(":", "ः")
        h = re.sub(r"[।|॥]", " ", h)
        h = " ".join(h.split())
        if h: res.append(h)
    return res

g = json.load(open(a.gita))
want = set(a.verses.split(",")) if a.verses else None
verses = []
for e in g:
    vid = f'{e["chapter"]}.{e["shloka"]}'
    if want and vid not in want: continue
    if not (a.all or want): continue
    verses.append((vid, halves(e["sanskrit"])))
shards = [[] for _ in range(a.split)]
for k, (vid, hs) in enumerate(verses):
    for i, h in enumerate(hs):
        shards[k % a.split].append({"id": f"{vid}_p{i}", "meter": meter_for(n_akshara(h)), "padas": [h], "seed": 60,
                                    "no_sandhi": True, "out": f"{a.wavdir}/{vid}_p{i}.wav"})
if a.split == 1:
    json.dump(shards[0], open(a.out, "w"), ensure_ascii=False, indent=1)
else:
    for k, s in enumerate(shards): json.dump(s, open(f"{a.out}.{k}", "w"), ensure_ascii=False, indent=1)
print(len(verses), "verses,", sum(len(s) for s in shards), "clips")
