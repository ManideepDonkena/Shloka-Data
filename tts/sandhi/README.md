# Sandhi split: sanskrit_parser vs the book's own word-for-word

`split_all.py` runs [sanskrit_parser](https://github.com/kmadathil/sanskrit_parser) on every half-verse (the chanted words joined, as in the audio) and keeps, of its top 12 splits, the one closest to the book's forms. `parser_vs_book.json` has both lists and an agreement ratio per half.

Result on all 657 verses (1,400 halves): parser produced a split for 1,303; **exact agreement on 233 (17%)**, mean ratio 0.71.
Typical gaps: the parser splits compounds differently (`maheṣvāsāḥ` vs `mahā iṣu āsāḥ`), and without its scoring models (gensim/sentencepiece not installed) its candidate ranking is poor (`viśiṣṭāḥ ye` → `viśiṣṭa āyetām`).

Conclusion: the book-derived split used by the app's "Sandhi split" toggle is the better source. The parser is useful only to flag halves where the two disagree strongly (agreement < 0.6) for a human check.
Jivnesh's SanskritShala/TransLIST would likely rank better, but their models are behind Drive/SharePoint downloads and a Python 3.7 stack (not run).
Setup quirk: sanskrit_parser 0.2.x hard-codes `'SLP1'`; with current indic_transliteration the scheme names are lower-case, hence the alias loop in the script.
