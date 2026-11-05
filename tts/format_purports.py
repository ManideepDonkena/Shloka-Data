"""Break the long purport blocks of gita.json into readable paragraphs -> poc/purports.json
(paragraphs separated by a blank line). Existing line breaks are kept; blocks longer than ~650 characters are cut at sentence
ends into paragraphs of roughly 3-4 sentences.   python tts/format_purports.py gita.json poc/purports.json"""
import json, re, sys
ABBR = {"bg", "sb", "cc", "viz", "i.e", "e.g", "cf", "dr", "st", "vs", "no", "vol", "p", "pp", "ca", "ibid", "skt", "ch", "mr", "etc", "śrī", "śri", "sri"}
SENT = re.compile(r"(?<=[.?!])([\"”’)\]]*)\s+(?=[\"“‘(\[]?[A-ZŚṚĀĪŪṆṬḌṢḤ])")


def sentences(t):
    out, last = [], 0
    for m in SENT.finditer(t):
        head = t[last:m.start()]
        w = re.findall(r"[\wāīūṛṝḷḹṅñṭḍṇśṣḥṁṃ.]+$", head)
        if w and w[0].rstrip(".").lower() in ABBR and len(w[0].rstrip(".")) <= 4 and not head.endswith(("?", "!")):
            continue
        out.append(t[last:m.end()].strip()); last = m.end()
    if t[last:].strip(): out.append(t[last:].strip())
    return out


def paras(block, target=420, hard=700):
    if len(block) <= 650: return [block]
    res, cur = [], ""
    for s in sentences(block):
        if cur and len(cur) + len(s) + 1 > hard or len(cur) >= target:
            res.append(cur); cur = ""
        cur = (cur + " " + s).strip()
    if cur:
        if res and len(cur) < 120: res[-1] += " " + cur
        else: res.append(cur)
    return res


def tidy(t):
    t = re.sub(r"[ \t]+", " ", t.replace("\r", "")).strip()
    return re.sub(r"\s+([,.;:?!])", r"\1", t)


if __name__ == "__main__":
    g = json.load(open(sys.argv[1])); out = {}
    for v in g:
        blocks = [tidy(b) for b in re.split(r"\n+", v["purport"]) if b.strip()]
        out[f"{v['chapter']}.{v['shloka']}"] = "\n\n".join(p for b in blocks for p in paras(b))
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
    n = [len(x.split("\n\n")) for x in out.values()]
    print(len(out), "purports; paragraphs total", sum(n), "max", max(n))
