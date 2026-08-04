"""Deterministically map sandhi-split `synonyms` keys onto the sandhi-joined
verse surface tokens, keeping line structure. No ML, no LLM.

Output per verse: lines -> tokens -> which synonym key(s) each token carries.
"""
import json, re, sys, unicodedata
from functools import lru_cache

# IAST -> ASCII skeleton. Sandhi mostly mutates the *final* segment of a word,
# so we fold everything to a coarse skeleton and let edit distance absorb it.
FOLD = {
    "ā": "a", "ī": "i", "ū": "u", "ṛ": "r", "ṝ": "r", "ḷ": "l", "ḹ": "l",
    "ṅ": "n", "ñ": "n", "ṇ": "n", "ṁ": "m", "ṃ": "m", "ḥ": "h",
    "ṭ": "t", "ḍ": "d", "ś": "s", "ṣ": "s", "ē": "e", "ō": "o",
}


def fold(s):
    s = unicodedata.normalize("NFC", s.lower())
    # avagraha marks an elided word-initial a-: "’haṁ" is really "aham"
    s = re.sub(r"(^|\s)[\u2019\u02bc\'`]", r"\1a", s)
    out = "".join(FOLD.get(c, c) for c in s)
    out = re.sub(r"[^a-z ]", "", out)
    return out


def skeleton(s):
    """Collapse the sandhi-volatile word-final material."""
    w = fold(s).replace(" ", "")
    # visarga / anusvara / final glide all alternate freely across sandhi
    w = re.sub(r"(h|s|r|m|n|o)$", "", w)
    # long/short vowel alternation at the join
    w = re.sub(r"(a|i|u|e|o)$", "", w)
    return w


@lru_cache(maxsize=None)
def edit(a, b):
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cost(syn_chunk, tok_chunk):
    """Dissimilarity of a group of synonym keys vs a group of verse tokens."""
    a, b = skeleton(syn_chunk), skeleton(tok_chunk)
    if not a and not b:
        return 0.0
    d = edit(a, b)
    base = max(len(a), len(b), 1)
    # full-form comparison as a tie-breaker
    fa, fb = fold(syn_chunk).replace(" ", ""), fold(tok_chunk).replace(" ", "")
    e2 = edit(fa, fb)
    d2 = e2 / max(len(fa), len(fb), 1)
    total = d / base + 0.25 * d2
    # A single-character difference IS ordinary sandhi (tat/tad, tu/tv, aham/ahaṁ).
    # Length-normalising punishes short words for it, so floor those cases.
    if e2 <= 1 and min(len(fa), len(fb)) >= 2:
        total = min(total, 0.15)
    return total


MAXG = 3  # at most 3 synonyms <-> 3 tokens in one group (ca+eva -> caiva etc.)


def align(syns, tokens):
    """Monotonic many-to-many alignment. Returns list of (syn_idx[], tok_idx[])."""
    n, m = len(syns), len(tokens)
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            for gi in range(1, MAXG + 1):
                if i + gi > n:
                    break
                for gj in range(1, MAXG + 1):
                    if j + gj > m:
                        break
                    c = cost(" ".join(syns[i:i + gi]), " ".join(tokens[j:j + gj]))
                    # prefer 1:1
                    c += 0.15 * (gi - 1) + 0.15 * (gj - 1)
                    if dp[i][j] + c < dp[i + gi][j + gj]:
                        dp[i + gi][j + gj] = dp[i][j] + c
                        bk[i + gi][j + gj] = (i, j, gi, gj)
            # REPEAT edge: `synonyms` is a JSON object, so a word occurring
            # twice in the verse survives only once. Let a token group re-use
            # any synonym key without consuming it.
            for gj in range(1, MAXG + 1):
                if j + gj > m:
                    break
                tok = " ".join(tokens[j:j + gj])
                best, bidx = INF, None
                for k, s in enumerate(syns):
                    c = cost(s, tok)
                    if c < best:
                        best, bidx = c, k
                c = best + 0.30 + 0.15 * (gj - 1)   # penalty: prefer consuming
                if dp[i][j] + c < dp[i][j + gj]:
                    dp[i][j + gj] = dp[i][j] + c
                    bk[i][j + gj] = (i, j, 0, gj, bidx)
    if dp[n][m] == INF:
        return None, INF
    path, i, j = [], n, m
    while (i, j) != (0, 0):
        step = bk[i][j]
        pi, pj, gi, gj = step[:4]
        syn_idx = list(range(pi, pi + gi)) if gi else [step[4]]
        path.append((syn_idx, list(range(pj, pj + gj)), gi == 0))
        i, j = pi, pj
    path.reverse()
    return path, dp[n][m] / max(m, 1)


def best_local(tok, syns):
    """Best single / adjacent-pair / adjacent-triple synonym match for ONE token,
    searched over the whole list regardless of position."""
    best, at = float("inf"), None
    n = len(syns)
    for k in range(n):
        for g in (1, 2, 3):
            if k + g > n:
                break
            c = cost(" ".join(syns[k:k + g]), tok)
            if c < best:
                best, at = c, list(range(k, k + g))
    # non-adjacent pairs, for compounds whose halves sit apart in the dict
    for a in range(n):
        for b in range(n):
            if a == b or b == a + 1:
                continue
            c = cost(syns[a] + " " + syns[b], tok) + 0.02
            if c < best:
                best, at = c, [a, b]
    return best, at


def repair(path, syns, tokens, thresh=0.35, margin=0.08):
    """Second text-matching pass.

    The DP must consume every synonym in dict order. When that order desyncs
    from the verse (combined verses, sense-ordered synonym lists), every later
    group is dragged along -- e.g. `yoddhu-kāmān` getting `mayā + saha +
    yoddhavyam` even though an exact `yoddhu-kāmān` key exists. So for any group
    the DP is unsure about, re-match each token against the whole synonym list
    and take the better answer.
    """
    out = []
    for si, ti, rep in path:
        g_txt = " ".join(syns[k] for k in si)
        g_cost = cost(g_txt, " ".join(tokens[k] for k in ti))
        if g_cost < thresh:
            out.append((si, ti, rep, False))
            continue
        fixed, ok = [], True
        for t in ti:
            c, idx = best_local(tokens[t], syns)
            if idx is not None and c + margin < g_cost:
                fixed.append(([*idx], [t], True, True))
            else:
                ok = False
                break
        out.extend(fixed if (ok and fixed) else [(si, ti, rep, False)])
    return out


def refine(path, syns, tokens, tol=0.05):
    """Split an n:n group into 1:1 pairs when that costs no more.
    Keeps `paryāptaṁ tv <- paryāptam + tu` from showing both synonyms on both
    tokens, while leaving genuine 1:n groups (`caiva <- ca + eva`) alone."""
    out = []
    for si, ti, rep, fixed in path:
        if len(si) == len(ti) > 1:
            # concatenated matching always scores lower than the sum of parts,
            # so compare on plausibility instead: split when every 1:1 pair is
            # itself a believable match.
            per = [cost(syns[a], tokens[b]) for a, b in zip(si, ti)]
            if max(per) < 0.7:
                out.extend(([a], [b], rep, fixed) for a, b in zip(si, ti))
                continue
        out.append((si, ti, rep, fixed))
    return out


def verse_lines(verse):
    return [ln.strip() for ln in verse["english"].split("\n") if ln.strip()]


def build(verse):
    lines = verse_lines(verse)
    tokens, tok_line = [], []
    for li, ln in enumerate(lines):
        for t in ln.split():
            tokens.append(t)
            tok_line.append(li)
    syns = list(verse["synonyms"].keys())
    path, score = align(syns, tokens)
    if path is not None:
        path = refine(repair(path, syns, tokens), syns, tokens)
        tot = sum(cost(" ".join(syns[k] for k in si), " ".join(tokens[k] for k in ti))
                  for si, ti, _r, _f in path)
        score = tot / max(len(tokens), 1)
    return lines, tokens, tok_line, syns, path, score


if __name__ == "__main__":
    data = json.load(open("/home/manideep/Shloka-Data/gita.json"))
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        ch, sh = sys.argv[2], sys.argv[3]
        v = next(x for x in data if x["chapter"] == ch and x["shloka"] == sh)
        lines, tokens, tok_line, syns, path, score = build(v)
        print(f"BG {ch}.{sh}   align cost {score:.3f}\n")
        for li, ln in enumerate(lines):
            print(f"  line {li}: {ln}")
        print()
        for si, ti, rep, fixed in path:
            s = " + ".join(syns[k] for k in si)
            t = " ".join(tokens[k] for k in ti)
            ln = {tok_line[k] for k in ti}
            c = cost(" ".join(syns[k] for k in si), t)
            flag = "" if c < 0.35 else "   <-- weak"
            if rep:
                flag += "   (reused)"
            if fixed:
                flag += "   (repaired)"
            print(f"  L{sorted(ln)}  {t:<28} <- {s}{flag}")
        sys.exit()

    # whole-corpus validation
    good = weak = fail = 0
    worst = []
    for v in data:
        if "synonyms" not in v or not v.get("english"):
            fail += 1
            continue
        try:
            *_, path, score = build(v)
        except Exception:
            fail += 1
            continue
        if path is None:
            fail += 1
        elif score < 0.35:
            good += 1
        else:
            weak += 1
            worst.append((score, v["chapter"], v["shloka"]))
    tot = len(data)
    print(f"verses: {tot}")
    print(f"  clean alignment (cost<0.35): {good}  ({good/tot*100:.1f}%)")
    print(f"  weak (needs review):        {weak}  ({weak/tot*100:.1f}%)")
    print(f"  failed:                     {fail}")
    worst.sort(reverse=True)
    print("\nworst 10:")
    for s, c, sh in worst[:10]:
        print(f"  {c}.{sh}  cost {s:.3f}")
