"""mapping.json has no usable words for merged verses (gita.json 'english' only covers the first verse of 1.16-18 etc.).
Rebuild them from the Devanagari: transliterate to IAST, split each half-verse into 2 padas at the middle word, then run
the same sandhi/synonym mapper as build_mapping.py. Writes OUT (mapping-format records for the merged ids only)."""
import json, os, re, sys
POC = os.environ.get("POC", "/home/mani/shloka/Shloka-Data/poc"); sys.path.insert(0, POC)
from sandhi_map import build, cost as group_cost
from indic_transliteration import sanscript
OUT = sys.argv[1]; EXTRA = set(os.environ.get("EXTRA", "").split(","))
VOW = re.compile(r"(ai|au|[aāiīuūṛṝḷeo])")
def iast(s):
    s = re.sub("[‌‍]", "", s).replace(":", "ः")
    t = sanscript.transliterate(s, sanscript.DEVANAGARI, sanscript.IAST)
    return t.replace("'", "’").replace("-", " ")
def halves(sk):
    lines = [l.strip() for l in sk.split("\n") if l.strip()]
    out, cur = [], []
    for l in lines:
        if re.search(r"वाच\s*$", l): out.append(l); continue
        cur.append(l)
        if re.search(r"[।॥|]", l): out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out
def padas(h):
    h = re.sub(r"॥.*?॥", "", h); h = re.sub(r"[।|॥]", " ", h)
    ws = iast(h).split()
    if len(ws) < 2: return [" ".join(ws)]
    syl = [max(1, len(VOW.findall(w.lower()))) for w in ws]; tot = sum(syl); best, cum, k = 0, 0, 1
    for i in range(len(ws) - 1):
        cum += syl[i]
        if abs(cum - tot / 2) < abs((best or 10**9) - tot / 2) or i == 0: best, k = cum, i + 1
    return [" ".join(ws[:k]), " ".join(ws[k:])]
gita = json.load(open(os.path.join(POC, "..", "gita.json")))
res = []
for v in gita:
    vid = f'{v["chapter"]}.{v["shloka"]}'
    if "-" not in str(v["shloka"]) and vid not in EXTRA: continue
    lines = []
    for h in halves(v["sanskrit"]):
        if re.search(r"वाच\s*$", h): lines.append(iast(h)); continue
        lines += padas(h)
    v2 = dict(v, english="\n".join(lines))
    rec = {"id": vid, "chapter": v["chapter"], "shloka": v["shloka"], "sanskrit": v["sanskrit"], "english": v2["english"],
           "translation": v.get("translation", ""), "combined": True}
    try:
        ls, tokens, tok_line, syns, path, score = build(v2)
    except Exception as e:
        rec.update(status="failed", lines=[{"index": i, "text": l, "tokens": [{"token": w, "synonym": "", "meaning": ""} for w in l.split()]} for i, l in enumerate(lines)]); res.append(rec); continue
    info = {}
    for gi, (si, ti, rep, fixed) in enumerate(path or []):
        key = " + ".join(syns[k] for k in si); mean = " / ".join(v["synonyms"][syns[k]]["meaning"] for k in si)
        for t in ti: info[t] = {"synonym": key, "meaning": mean}
    rec["lines"] = [{"index": li, "text": ln, "tokens": [dict(token=tokens[t], **info.get(t, {"synonym": "", "meaning": ""}))
                     for t in range(len(tokens)) if tok_line[t] == li]} for li, ln in enumerate(ls)]
    rec["status"] = "rebuilt"; res.append(rec)
    n = sum(len(l["tokens"]) for l in rec["lines"]); m = sum(1 for l in rec["lines"] for t in l["tokens"] if t["meaning"])
    print(vid, f"{len(ls)} lines  {n} words  {m} with meaning  cost {score:.2f}" if path else f"{vid} NO PATH")
json.dump(res, open(OUT, "w"), ensure_ascii=False)
