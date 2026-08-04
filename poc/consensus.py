"""Cross-check two independent aligners against each other.

With only two loosely hand-tagged verses, there is no ground truth to score 258
verses against. But MMS (multilingual wav2vec2, roman characters) and Sushrota
(Sanskrit Conformer, Devanagari BPE) share no architecture, training data or
tokenizer. Where two such different models put a boundary in the same place,
that boundary is very likely right; where they diverge, something is wrong.

That gives a ground-truth-free quality signal for every verse, and a priority
order for hand-tagging: fix what the models disagree about.

    python3 consensus.py
"""
import json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
NEAR = 0.10          # boundaries within 100 ms count as agreement


def words_of(v):
    return [w for L in v["lines"] for C in L["chunks"] for w in C["words"]]


def main():
    a = {v["id"]: v for v in json.load(open(os.path.join(ROOT, "aligned_data.json")))}
    b = {v["id"]: v for v in json.load(open(os.path.join(ROOT, "sushrota_data.json")))}
    shared = sorted(set(a) & set(b), key=lambda i: tuple(int(x) for x in i.split(".")[:2]))

    rows, all_d = [], []
    for vid in shared:
        wa, wb = words_of(a[vid]), words_of(b[vid])
        if len(wa) != len(wb):
            continue
        d = []
        for x, y in zip(wa, wb):
            d.append(abs(x["word_audio"]["start"] - y["word_audio"]["start"]))
            d.append(abs(x["word_audio"]["end"] - y["word_audio"]["end"]))
        d = np.array(d)
        all_d.append(d)
        rows.append({
            "id": vid,
            "n": len(wa),
            "median_ms": float(np.median(d) * 1000),
            "agree": float((d <= NEAR).mean()),
            "mms_conf": a[vid].get("confidence", 0),
            "sus_conf": b[vid].get("confidence", 0),
            "mms_suspect": a[vid].get("suspect_words", 0),
            "sus_suspect": b[vid].get("suspect_words", 0),
        })

    D = np.concatenate(all_d)
    print(f"compared {len(rows)} verses, {len(D)//2} word boundaries x2\n")
    print("per-boundary difference between the two aligners:")
    for q in (50, 75, 90, 95):
        print(f"  p{q}: {np.percentile(D, q)*1000:7.0f} ms")
    for t in (0.05, 0.10, 0.25, 0.50):
        print(f"  within {int(t*1000):4d} ms: {(D <= t).mean()*100:5.1f}%")

    ag = np.array([r["agree"] for r in rows])
    print(f"\nper-verse agreement (fraction of boundaries within {int(NEAR*1000)} ms):")
    for t in (0.9, 0.75, 0.5, 0.25):
        print(f"  >= {t:.2f}: {(ag >= t).sum():3d} verses ({(ag>=t).mean()*100:.0f}%)")
    print(f"  median {np.median(ag):.2f}")

    # does agreement track the independent duration check?
    sus = np.array([r["mms_suspect"] + r["sus_suspect"] for r in rows])
    hi, lo = ag >= 0.75, ag < 0.5
    print(f"\nsuspect spans per verse where models agree (>=0.75): {sus[hi].mean():.2f}")
    print(f"                              where they diverge (<0.5): {sus[lo].mean():.2f}")

    rows.sort(key=lambda r: r["agree"])
    out = os.path.join(ROOT, "consensus.json")
    json.dump(rows, open(out, "w"), indent=1)
    print(f"\nwrote {os.path.basename(out)}")
    print("\nworst 10 — tag these first:")
    for r in rows[:10]:
        print(f"  BG {r['id']:<8} agree {r['agree']:.2f}  median {r['median_ms']:5.0f} ms"
              f"  ({r['n']} words)")
    print("\nbest 10 — most likely already correct:")
    for r in rows[-10:]:
        print(f"  BG {r['id']:<8} agree {r['agree']:.2f}  median {r['median_ms']:5.0f} ms")


if __name__ == "__main__":
    main()
