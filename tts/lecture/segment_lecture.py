"""Find, in a recorded Gītā class, where each verse is recited and where the speaker explains each word.

    python segment_lecture.py <video_id> <first_verse> <last_verse> <captions.json3> [out.json]

Idea (spoken-term search, as in IIT Kanpur MADHAV lab's audio-archive work): the YouTube auto-captions give a time for
every spoken word. The Sanskrit the speaker chants or quotes comes out in Devanagari, roughly spelled ("धीमताम योगी
नाम" for dhīmatāṁ yoginām). Every caption word and every verse word is reduced to a rough sound key (no vowel length,
ś/ṣ -> s, ṇ -> n, no final 'a' ...) and compared; neighbouring caption words are also tried joined (compounds get split).
  * recitation = a 30 s stretch that contains at least half of a verse's words;
  * a verse's section = from its first recitation to the next verse's first recitation;
  * a word's explanation = from its first mention in that section (after the recitation) to the next word's first mention.
Nothing is downloaded or re-hosted by the app: it stores times and plays the YouTube video itself.
"""
import difflib, json, re, sys, unicodedata
from indic_transliteration import sanscript

GITA = "/home/mani/shloka/Shloka-Data/gita.json"
TTS = "/home/mani/shloka/Shloka-Data/poc/tts_data.json"


def key(s, script="iast"):
    if script == "deva":
        s = sanscript.transliterate(s, sanscript.DEVANAGARI, sanscript.IAST)
    s = unicodedata.normalize("NFC", s.lower())
    for a, b in (("ṁ", "m"), ("ṃ", "m"), ("ṅ", "n"), ("ñ", "n"), ("ṇ", "n"), ("ś", "s"), ("ṣ", "s"), ("ṭ", "t"), ("ḍ", "d"),
                 ("ṛ", "ri"), ("ḥ", ""), ("ā", "a"), ("ī", "i"), ("ū", "u"), ("w", "v"), ("’", ""), ("'", "")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    s = re.sub(r"(.)\1+", r"\1", s)              # double letters
    s = re.sub(r"(?<=[^aeiou])a$", "", s)        # Hindi drops the final schwa
    s = re.sub(r"[mn]$", "m", s)
    return s


def similar(a, b):
    """Same sound key, or (for words of 6+ letters) close enough: auto-captions misspell long Sanskrit words."""
    if a == b:
        return True
    n = min(len(a), len(b))
    return n >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= (0.84 if n < 9 else 0.8)


def caption_words(path):
    j = json.load(open(path, encoding="utf-8"))
    out = []
    for e in j.get("events", []):
        t0 = e.get("tStartMs", 0)
        for s in e.get("segs") or []:
            text = s.get("utf8", "").strip()
            if not text or text.startswith("["):
                continue
            t_seg = (t0 + s.get("tOffsetMs", 0)) / 1000.0
            words = [w for w in re.split(r"[\s\n]+", text) if w]
            for wi, w in enumerate(words):
                out.append({"t": round(t_seg + wi * 0.15, 2), "w": w, "k": key(w, "deva")})
    return out


def verse_terms(v):
    """The words to look for: each chanted token, and the members of compounds (kept if 4+ letters)."""
    terms = []
    for l in v["lines"]:
        for c in l["chunks"]:
            for w in c["words"]:
                tok = w["token"]
                parts = [tok] + ([p for p in tok.split("-") if p] if "-" in tok else [])
                for p in parts:
                    k = key(p)
                    if len(k) >= 3 and k not in [t["k"] for t in terms]:
                        terms.append({"token": tok, "part": p, "k": k, "meaning": w.get("meaning", "")})
    return terms


def hits(words, terms):
    """(time, term index) for every caption word (or two joined) that sounds like a verse word."""
    res = []
    for i, cw in enumerate(words):
        cands = [cw["k"]] + ([cw["k"] + words[i + 1]["k"]] if i + 1 < len(words) and words[i + 1]["t"] - cw["t"] < 2 else [])
        for ti, t in enumerate(terms):
            if any(similar(c, t["k"]) for c in cands if c):
                res.append((cw["t"], ti))
    return res


def main(vid, first, last, caps, out=None, title=None, speaker=None, channel=None, url=None):
    tts = {v["id"]: v for v in json.load(open(TTS, encoding="utf-8"))}
    ch, a, b = first.split(".")[0], int(first.split(".")[1]), int(last.split(".")[1])
    ids = []
    for vid_ in tts.keys():
        if not vid_.startswith(f"{ch}."):
            continue
        rest = vid_.split(".")[1]
        if "-" in rest:
            p1, p2 = map(int, rest.split("-"))
            if max(a, p1) <= min(b, p2):
                ids.append(vid_)
        else:
            n = int(rest)
            if a <= n <= b:
                ids.append(vid_)
    ids.sort(key=lambda x: int(x.split(".")[1].split("-")[0]))
    words = caption_words(caps)
    end_all = words[-1]["t"] if words else 0
    found = {}
    for vid_ in ids:
        terms = verse_terms(tts[vid_])
        hs = hits(words, terms)
        # recitations: 30 s windows holding at least half the verse's distinct words
        rec = []
        for t0, _ in hs:
            got = {ti for t, ti in hs if t0 <= t < t0 + 30}
            if len(got) >= max(3, 0.5 * len({t["token"] for t in terms})):
                if not rec or t0 > rec[-1]["end"] + 5:
                    rec.append({"start": t0, "end": max(t for t, ti in hs if t0 <= t < t0 + 30), "cover": round(len(got) / len(terms), 2)})
                else:
                    rec[-1]["end"] = max(rec[-1]["end"], max(t for t, ti in hs if t0 <= t < t0 + 30))
        found[vid_] = {"terms": terms, "hits": hs, "recitations": rec}
    # verses heard only as discussion (no clear recitation): the first spot with 2+ of their words within 25 s
    for v in ids:
        f = found[v]
        if not f["recitations"]:
            hs = sorted(f["hits"])
            for t0, _ in hs:
                if len({ti for t, ti in hs if t0 <= t < t0 + 20}) >= 2:
                    f["recitations"] = [{"start": t0, "end": t0, "cover": 0, "discussed_only": True}]
                    break
    order = sorted([v for v in ids if found[v]["recitations"]], key=lambda v: found[v]["recitations"][0]["start"])
    # verses recited together (first recitations within 75 s) share one commentary block
    blocks = []
    for v in order:
        t = found[v]["recitations"][0]["start"]
        if blocks and t - found[blocks[-1][-1]]["recitations"][0]["start"] < 75:
            blocks[-1].append(v)
        else:
            blocks.append([v])
    verses = {}
    for bi, blk in enumerate(blocks):
        b0 = found[blk[0]]["recitations"][0]["start"]
        nxt = found[blocks[bi + 1][0]]["recitations"][0]["start"] - 3 if bi + 1 < len(blocks) else end_all
        last_hit = max([t for v in blk for t, _ in found[v]["hits"] if b0 <= t < nxt] or [b0])
        b1 = min(nxt, last_hit + 90)            # stop after the last mention: stories and Q&A are not this verse
        for v in blk:
            f = found[v]
            s0 = max(0.0, f["recitations"][0]["start"] - 3)
            rec_end = max(r["end"] for r in f["recitations"] if r["start"] < b1)
            first = {}
            for t, ti in sorted(f["hits"]):
                tok = f["terms"][ti]["token"]
                if rec_end + 2 < t < b1 and tok not in first:
                    first[tok] = t
            seq = sorted(first.items(), key=lambda x: x[1])
            wl = {}
            for j, (tok, t) in enumerate(seq):
                e = min(seq[j + 1][1] - 1 if j + 1 < len(seq) else b1, t + 240, b1)
                if e - t < 8:
                    e = min(t + 20, b1)
                snip = " ".join(w["w"] for w in words if t - 1 <= w["t"] < min(e, t + 12))
                wl[tok] = [{"start": round(max(s0, t - 2), 1), "end": round(e, 1), "said": snip[:140]}]
            verses[v] = {"start": round(s0, 1), "end": round(b1, 1), "recited": not f["recitations"][0].get("discussed_only"),
                         "together_with": [x for x in blk if x != v], "recitations": f["recitations"], "words": wl}
    res = {"video": vid, "verses": verses, "missing": [v for v in ids if v not in verses]}
    if title:
        res["title"] = title
    if speaker:
        res["speaker"] = speaker
    if channel:
        res["channel"] = channel
    if url:
        res["url"] = url
    res["language"] = "Hindi"
    res["source"] = "auto: YouTube captions matched to the verse words (tts/lecture/segment_lecture.py); check and trim in lecture_editor.html"
    if out:
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    r = main(*sys.argv[1:6])
    for v, d in r["verses"].items():
        mm = lambda s: "%d:%02d" % (s // 60, s % 60)
        print(v, mm(d["start"]), "-", mm(d["end"]), "recited", [(mm(x["start"]), x["cover"]) for x in d["recitations"]][:4], "| words explained:", len(d["words"]))
    print("missing:", r["missing"])
