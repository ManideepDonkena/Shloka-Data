"""Sandhi viccheda for every half-verse with sanskrit_parser (pip install sanskrit_parser), checked against the book.

For each half (the chanted words joined without spaces) the parser proposes splits; we keep the one closest to the book's own
word-for-word forms (poc/tts_data.json synonyms) and report how well they agree.
    python split_all.py out.json
Needs the scheme-name alias below because sanskrit_parser 0.2.x hardcodes 'SLP1' but newer indic_transliteration lower-cases it."""
import difflib, json, logging, re, sys, time, unicodedata, warnings
warnings.filterwarnings("ignore"); logging.disable(logging.CRITICAL)
from indic_transliteration import sanscript as S
for k in list(S.SCHEMES): S.SCHEMES.setdefault(k.upper(), S.SCHEMES[k])
from sanskrit_parser import Parser

TTS = sys.argv[2] if len(sys.argv) > 2 else "../../poc/tts_data.json"
P = Parser(input_encoding="SLP1", output_encoding="SLP1", lexical_lookup="sanskrit_data")
norm = lambda w: unicodedata.normalize("NFC", w).lower().replace("ṁ", "m").replace("’", "a").replace("'", "a")
to_slp = lambda s: S.transliterate(s, "iast", "slp1")
to_iast = lambda s: S.transliterate(s, "slp1", "iast")


def book_words(words):
    out, seen = [], None
    for w in words:
        sy = (w.get("synonym") or w["token"]).strip()
        if sy == seen: continue
        seen = sy
        out += [norm(x) for x in re.split(r"[\s+\-]+", sy) if x]
    return out


res, t0 = {}, time.time()
data = json.load(open(TTS))
for n, v in enumerate(data):
    halves = []
    for h in range(0, len(v["lines"]), 2):
        ws = [w for l in v["lines"][h:h + 2] for c in l["chunks"] for w in c["words"]]
        if not ws: continue
        joined = norm("".join(w["token"].replace("-", "") for w in ws))
        book = book_words(ws)
        best = None
        try:
            for sp in (P.split(to_slp(joined), limit=12) or []):
                cand = [norm(to_iast(str(x))) for x in sp.split_object.tokens] if hasattr(sp, "split_object") else []
                if not cand:
                    cand = [norm(to_iast(x)) for x in re.findall(r"[^\[\]', ]+", str(sp))]
                r = difflib.SequenceMatcher(None, cand, book).ratio()
                if best is None or r > best[0]: best = (r, cand)
        except Exception as e:
            best = None
        halves.append({"book": book, "parser": best[1] if best else None, "agree": round(best[0], 2) if best else None})
    res[v["id"]] = halves
    if n % 25 == 0: print(n, round(time.time() - t0), "s", flush=True)
json.dump(res, open(sys.argv[1], "w"), ensure_ascii=False)
