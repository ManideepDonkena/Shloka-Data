"""Flag implausible word spans in an alignment file.

The CTC score answers "is this the right word here?" but says nothing about
whether the *span* is sane. A 19 s word scored 0.33 and an 18.8 s word scored
0.76 -- confidence alone cannot separate good verses from broken ones.

Sanskrit is near-isochronous per syllable within one recitation, so the honest
independent check is: does each word last roughly syllables x (this verse's
median seconds-per-syllable)? Words far off that are almost always the aligner
stretching across a pause.

    python3 flag_spans.py aligned_data.json
"""
import json, re, sys, os
import numpy as np

VOWELS = re.compile(r"(ai|au|[aāiīuūṛṝḷeo])")
HI, LO = 2.5, 0.4          # allowed ratio band around the expected duration


def syllables(w):
    return max(1, len(VOWELS.findall(w.lower())))


def flag(path):
    data = json.load(open(path, encoding="utf-8"))
    stats = {"words": 0, "flagged": 0, "verses": 0, "clean": 0}

    for v in data:
        words = [w for L in v["lines"] for C in L["chunks"] for w in C["words"]]
        if not words:
            continue
        rate = []
        for w in words:
            d = w["word_audio"]["end"] - w["word_audio"]["start"]
            rate.append(d / syllables(w["token"]))
        med = float(np.median(rate)) or 1e-6

        nflag = 0
        for w, r in zip(words, rate):
            ratio = r / med
            w["dur_ratio"] = round(float(ratio), 2)
            bad = ratio > HI or ratio < LO
            w["suspect"] = bool(bad)
            nflag += bad
        stats["words"] += len(words)
        stats["flagged"] += nflag
        stats["verses"] += 1
        stats["clean"] += (nflag == 0)

        v["suspect_words"] = int(nflag)
        v["sec_per_syllable"] = round(med, 3)
        # a review score that actually discriminates: blend CTC confidence with
        # the fraction of words whose span looks physically wrong
        frac_ok = 1.0 - nflag / len(words)
        v["review_score"] = round(float(v.get("confidence", 0)) * frac_ok, 3)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    rs = np.array([v.get("review_score", 0) for v in data])
    print(f"{os.path.basename(path)}: {stats['verses']} verses, {stats['words']} words")
    print(f"  suspect word spans: {stats['flagged']} ({stats['flagged']/stats['words']*100:.1f}%)")
    print(f"  verses with none:   {stats['clean']} ({stats['clean']/stats['verses']*100:.0f}%)")
    for t in (0.7, 0.6, 0.5):
        print(f"  review_score >= {t}: {(rs>=t).sum()} ({(rs>=t).mean()*100:.0f}%)")
    print(f"  median review_score {np.median(rs):.2f}")
    worst = sorted(data, key=lambda v: v.get("review_score", 0))[:8]
    print("  worst: " + ", ".join(f"{v['id']}({v['review_score']})" for v in worst))


if __name__ == "__main__":
    for p in (sys.argv[1:] or ["aligned_data.json"]):
        flag(os.path.join(os.path.dirname(os.path.abspath(__file__)), p))
