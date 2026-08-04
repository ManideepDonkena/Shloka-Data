"""Emit mapping.json: sandhi/synonym mapping for every verse in gita.json.

Text-only, so it covers all 657 verses regardless of whether audio is tagged.
Used by the QA tab to eyeball where the deterministic mapper is unsure.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sandhi_map import build, cost as group_cost

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
WEAK = 0.35


def run():
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    audio_ids = {"1.14", "18.66"}
    out, stats = [], {"clean": 0, "weak": 0, "failed": 0}

    for v in gita:
        vid = f"{v['chapter']}.{v['shloka']}"
        rec = {
            "id": vid, "chapter": v["chapter"], "shloka": v["shloka"],
            "sanskrit": v.get("sanskrit", ""), "english": v.get("english", ""),
            "translation": v.get("translation", ""),
            "has_audio": vid in audio_ids,
            "combined": "-" in str(v.get("shloka", "")),
        }
        try:
            lines, tokens, tok_line, syns, path, score = build(v)
        except Exception as exc:
            rec.update(status="failed", error=str(exc)[:120], cost=None, lines=[])
            stats["failed"] += 1
            out.append(rec)
            continue

        if path is None:
            rec.update(status="failed", error="no alignment", cost=None, lines=[])
            stats["failed"] += 1
            out.append(rec)
            continue

        tok_info = {}
        for gi, (si, ti, rep, fixed) in enumerate(path):
            key = " + ".join(syns[k] for k in si)
            mean = " / ".join(v["synonyms"][syns[k]]["meaning"] for k in si)
            c = group_cost(" ".join(syns[k] for k in si),
                           " ".join(tokens[k] for k in ti))
            for t in ti:
                tok_info[t] = {"synonym": key, "meaning": mean,
                               "cost": round(c, 3), "repeat": bool(rep),
                               "fixed": bool(fixed), "group": gi,
                               "span": len(ti) > 1 or len(si) > 1}

        rec["lines"] = [
            {"index": li, "text": ln,
             "tokens": [dict(token=tokens[t], **tok_info.get(t, {
                 "synonym": "", "meaning": "", "cost": None,
                 "repeat": False, "fixed": False, "group": -1, "span": False}))
                 for t in range(len(tokens)) if tok_line[t] == li]}
            for li, ln in enumerate(lines)
        ]
        rec["cost"] = round(score, 3)
        # a verse is "weak" if the whole-verse cost is high OR any group is bad
        worst = max((t["cost"] or 0) for l in rec["lines"] for t in l["tokens"]) \
            if any(l["tokens"] for l in rec["lines"]) else 0
        rec["worst_group"] = round(worst, 3)
        rec["status"] = "clean" if (score < WEAK and worst < WEAK) else "weak"
        stats[rec["status"]] += 1
        out.append(rec)

    with open(os.path.join(ROOT, "mapping.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(os.path.join(ROOT, "mapping.json")) / 1e6
    print(f"verses {len(out)}  clean {stats['clean']}  weak {stats['weak']}  "
          f"failed {stats['failed']}")
    print(f"wrote mapping.json ({size:.2f} MB)")


if __name__ == "__main__":
    run()
