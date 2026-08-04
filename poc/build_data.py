"""Build hierarchical memorization data for the POC.

Produces, per verse, a nested structure from ONE audio file:

    verse   -> whole recitation pass          (natural tempo)
      line  -> 4 lines, from pass A           (detected pauses)
        chunk -> half-line, from pass B       (hand-tagged, slow tempo)
          word  -> individual word            (valley split inside a chunk)

Every word also carries its sandhi-resolved synonym key and meaning, via
sandhi_map (deterministic, no ML).
"""
import json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gapdetect import decode, stft_mag, smooth, SR, HOP, NFFT
from sandhi_map import build as sandhi_build, fold

FPS = 100.0
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)

VOWELS = re.compile(r"(ai|au|[aāiīuūṛṝḷeo])")


def syllables(word):
    return max(1, len(VOWELS.findall(word.lower())))


def vocal_db(y):
    S = stft_mag(y)
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (freqs >= 300) & (freqs <= 3500)
    floor = np.percentile(S, 15, axis=0, keepdims=True)
    resid = np.maximum(S - floor, 1e-8)
    return 20 * np.log10(np.sqrt((resid[:, band] ** 2).mean(axis=1)) + 1e-8)


def split_chunk(db, a, b, words):
    """Split [a,b] into len(words) spans. Prefer energy valleys; fall back to
    a syllable-weighted proportional split. Returns (spans, method)."""
    k = len(words)
    if k == 1:
        return [(a, b)], "chunk"

    w = np.array([syllables(t) for t in words], dtype=float)
    expected = np.cumsum(w)[:-1] / w.sum()          # expected internal cut points

    i, j = int(a * FPS), int(b * FPS)
    x = smooth(db[i:j], 7)
    n = len(x)

    # Collect every plausible dip, each with a depth score.
    cand = {}
    if n > 20:
        for pct in (25, 30, 35, 40, 45, 50, 55):
            thr = np.percentile(x, pct)
            d = np.diff((x < thr).astype(np.int8), prepend=0, append=0)
            runs = list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))
            merged = []
            for s, e in runs:
                if merged and (s - merged[-1][1]) / FPS < 0.10:
                    merged[-1] = (merged[-1][0], e)
                else:
                    merged.append((s, e))
            for s, e in merged:
                if (e - s) / FPS < 0.05 or s / FPS < 0.15 or e / FPS > n / FPS - 0.15:
                    continue
                depth = float((thr - x[s:e]).sum())
                key = (round(s / 5), round(e / 5))
                if depth > cand.get(key, (0, None, None))[0]:
                    cand[key] = (depth, s, e)

    dips = sorted((s, e, dep) for dep, s, e in cand.values())
    if len(dips) >= k - 1:
        maxdep = max(d[2] for d in dips) or 1.0
        best, best_combo = None, None
        from itertools import combinations
        for combo in combinations(range(len(dips)), k - 1):
            cuts = np.array([(dips[c][0] + dips[c][1]) / 2 / n for c in combo])
            if np.any(np.diff(cuts) <= 0):
                continue
            # how far the split is from what syllable counts predict
            shape = float(np.abs(cuts - expected).sum())
            # prefer deeper dips, but only as a tie-break
            depth = float(np.mean([dips[c][2] for c in combo])) / maxdep
            score = shape - 0.15 * depth
            if best is None or score < best:
                best, best_combo = score, combo
        # accept only if the split roughly matches the expected shape
        if best_combo is not None and best < 0.12 * (k - 1):
            gaps = sorted((dips[c][0], dips[c][1]) for c in best_combo)
            bounds = [0] + [g for gp in gaps for g in gp] + [n]
            spans = [(a + bounds[m] / FPS, a + bounds[m + 1] / FPS)
                     for m in range(0, len(bounds) - 1, 2)]
            if all(e - s > 0.12 for s, e in spans):
                return spans, "valley"

    edges = a + (b - a) * np.concatenate([[0], np.cumsum(w) / w.sum()])
    return [(edges[m], edges[m + 1]) for m in range(k)], "proportional"


def load_tagged(path):
    d = json.load(open(path))
    return d, [(s["start"] / 1000, s["end"] / 1000, s["label"]) for s in d["segments"]]


def match_tokens(label, tokens, cursor):
    """Find where a chunk label sits in the verse token list, from `cursor` on."""
    lab = [fold(t) for t in label.split()]
    for start in range(cursor, len(tokens) - len(lab) + 1):
        if [fold(t) for t in tokens[start:start + len(lab)]] == lab:
            return start, start + len(lab)
    return None


def build_verse(chapter, shloka, audio_rel, tagged_path, gita):
    verse = next(v for v in gita
                 if v["chapter"] == chapter and v["shloka"] == shloka)
    lines, tokens, tok_line, syns, path, cost = sandhi_build(verse)

    # token index -> (synonym key, meaning)
    meaning = {}
    for si, ti, _rep, _fixed in path:
        key = " + ".join(syns[k] for k in si)
        mean = " / ".join(verse["synonyms"][syns[k]]["meaning"] for k in si)
        for t in ti:
            meaning[t] = (key, mean)

    tagged, segs = load_tagged(os.path.join(REPO, tagged_path))
    y = decode(os.path.join(ROOT, audio_rel))
    db = vocal_db(y)

    # pass A = the leading segments whose labels are whole lines
    line_texts = [ln for ln in lines]
    passA, passB = [], []
    for a, b, lab in segs:
        (passA if fold(lab) in {fold(x) for x in line_texts} else passB).append((a, b, lab))
    passA.sort()
    passB.sort()

    out_lines = []
    cursor = 0
    for li, ln in enumerate(line_texts):
        span = next((s for s in passA if fold(s[2]) == fold(ln)), None)
        n_tok = len(ln.split())
        rng = match_tokens(ln, tokens, 0)
        out_lines.append({
            "index": li,
            "text": ln,
            "line_audio": {"start": round(span[0], 3), "end": round(span[1], 3)} if span else None,
            "chunks": [],
            "token_range": list(rng) if rng else None,
        })

    # attach pass-B chunks to their line, and split each into words
    cursor = 0
    for a, b, lab in passB:
        rng = match_tokens(lab, tokens, cursor)
        if rng is None:
            rng = match_tokens(lab, tokens, 0)
        if rng is None:
            continue
        cursor = rng[1]
        li = tok_line[rng[0]]
        words = tokens[rng[0]:rng[1]]
        spans, method = split_chunk(db, a, b, words)
        chunk = {
            "text": lab,
            "chunk_audio": {"start": round(a, 3), "end": round(b, 3)},
            "split_method": method,
            "words": [],
        }
        for n, (ws, we) in enumerate(spans):
            ti = rng[0] + n
            key, mean = meaning.get(ti, ("", ""))
            chunk["words"].append({
                "token": tokens[ti],
                "synonym": key,
                "meaning": mean,
                "word_audio": {"start": round(ws, 3), "end": round(we, 3)},
                "exact": method != "proportional" or len(words) == 1,
            })
        out_lines[li]["chunks"].append(chunk)

    verse_span = None
    if passA:
        verse_span = {"start": round(min(s[0] for s in passA), 3),
                      "end": round(max(s[1] for s in passA), 3)}

    return {
        "id": f"{chapter}.{shloka}",
        "chapter": chapter,
        "shloka": shloka,
        "audio": audio_rel,
        "sanskrit": verse.get("sanskrit", ""),
        "translation": verse.get("translation", ""),
        "align_cost": round(cost, 3),
        "verse_audio": verse_span,
        "lines": out_lines,
        "synonyms": [{"key": k, "meaning": v["meaning"]}
                     for k, v in verse["synonyms"].items()],
    }


if __name__ == "__main__":
    gita = json.load(open(os.path.join(REPO, "gita.json")))
    targets = [
        ("1", "14", "audio/1.14.mp3", "tagged_gita_1_14.json"),
        ("18", "66", "audio/18.66.mp3", "tagged_gita_18_66.json"),
    ]
    out = []
    for ch, sh, aud, tag in targets:
        v = build_verse(ch, sh, aud, tag, gita)
        out.append(v)
        nw = sum(len(c["words"]) for l in v["lines"] for c in l["chunks"])
        meth = {}
        for l in v["lines"]:
            for c in l["chunks"]:
                meth[c["split_method"]] = meth.get(c["split_method"], 0) + 1
        print(f"BG {v['id']}: {len(v['lines'])} lines, "
              f"{sum(len(l['chunks']) for l in v['lines'])} chunks, {nw} words, "
              f"align_cost={v['align_cost']}, splits={meth}")

    with open(os.path.join(ROOT, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nwrote {os.path.join(ROOT, 'data.json')}")
