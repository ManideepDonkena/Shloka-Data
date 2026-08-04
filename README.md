# Shloka Data

Bhagavad-gītā recitations, verse text, and a memorization app built on top of them.

**→ [`poc/`](poc/) — the app, the alignment pipeline, and what was measured.**

Open the hosted app at `https://<user>.github.io/Shloka-Data/poc/`, or run it
locally:

```bash
cd poc && python3 server.py     # http://localhost:8765
```

## Contents

| | |
|---|---|
| [`poc/`](poc/) | verse-learner app + forced-alignment pipeline ([README](poc/README.md)) |
| `BrajaBeats_Gita_MP3/` | 289 recitations, one per verse |
| `gita.json` | 657 verses: Devanagari, IAST, synonyms, translation, purport |
| `tags.json` | as above, working copy |
| `tagged_gita_*.json` | the two hand-tagged verses (the current benchmark) |
| `waveform_tagger.py`, `tagger_2.py` | original tkinter taggers, superseded by the web Tag editor |
| `downloader.ipynb`, `chage_name.py` | how the audio was fetched and renamed |

Each recording contains the verse twice — once line-paced, then slowly
word-by-word with call-and-response echoes — over a continuous drone with no
silence anywhere. That shapes everything in `poc/`.
