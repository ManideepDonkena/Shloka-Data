# Shloka Data

Bhagavad-gītā recitations, verse text, and a memorization app built on top of
them. Nothing here is hand-curated except two benchmark verses — every other
artifact is produced by a script in this repo and can be rebuilt.

**→ [`poc/`](poc/) — the app, the alignment pipeline, and what was measured.**

Open the hosted app at `https://manideepdonkena.github.io/Shloka-Data/poc/`, or
run it locally:

```bash
git clone https://github.com/ManideepDonkena/Shloka-Data.git
cd Shloka-Data/poc && python3 server.py     # http://localhost:8765
```

Nothing beyond the Python standard library is needed to *use* the app. The
alignment models are only needed to *regenerate* the tags — see
[`poc/README.md`](poc/README.md#run-it-locally).

## Contents

| | |
|---|---|
| [`poc/`](poc/) | verse-learner app + forced-alignment pipeline ([README](poc/README.md)) |
| `BrajaBeats_Gita_MP3/` | 286 recitations, one per verse (plus 3 stray download fragments) |
| `gita.json` | 657 verses: Devanagari, IAST, synonyms, translation, purport |
| `tags.json` | as above, working copy |
| `tagged_gita_*.json` | the two hand-tagged verses (the current benchmark) |
| `waveform_tagger.py`, `tagger_2.py` | original tkinter taggers, superseded by the web Tag editor |
| `downloader.ipynb`, `chage_name.py` | how the audio was fetched and renamed |

---

## Where each artifact came from

Two things were acquired from outside; everything else is derived from them.

### 1. Audio — `BrajaBeats_Gita_MP3/`

Downloaded from the [BrajaBeats](https://www.youtube.com/@BrajaBeats/shorts)
YouTube Shorts channel with `yt-dlp` ([`downloader.ipynb`](downloader.ipynb)):

```python
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'}],
    'match_filter': lambda info: None if 'Bhagavad-gita' in info.get('title','') else 'skip',
    'outtmpl': 'BrajaBeats_Gita_MP3/%(title)s.%(ext)s',
}
```

The filter both selects Gītā videos and skips titles already on disk, so the
notebook is re-runnable to pick up new uploads.
[`chage_name.py`](chage_name.py) then strips the YouTube ID and hashtag tail
from each filename:

```
Bhagavad-gita 2.20#shorts #gita [dQw4w9WgXcQ].mp3   →   Bhagavad-gita 2.20.mp3
```

The filename **is** the join key. Everything downstream matches audio to text
with `re.search(r"(\d+)\.(\d+)", filename)` → `chapter.verse` → `gita.json`.
286 of the 289 files match; the 3 leftovers are interrupted `.mp4.part`
download fragments and are ignored.

The rename was only partly applied — 54 filenames still carry a `#shorts …`
tail. It does not affect the join (the regex reads the number first), but it
does mean **audio URLs must be percent-encoded**, since a raw `#` in a URL
starts the fragment. The app does this; anything else reading these files must
too.

The channel does not cover the whole Gītā. There are 286 recordings against
657 verses, so most verses have text and meanings but no audio.

### 2. Text, synonyms, translation — `gita.json`

657 entries in the Bhaktivedanta edition's structure, one per verse:

```json
{
  "chapter": "1", "shloka": "1",
  "sanskrit":  "धर्मक्षेत्रे कुरुक्षेत्रे …",          // Devanagari, newline per line
  "english":   "dharma-kṣetre kuru-kṣetre\n…",      // IAST, newline per line
  "synonyms":  {"dharma-kṣetre": {"meaning": "in the place of pilgrimage", …}},
  "translation": "…", "purport": "…"
}
```

The `synonyms` block is the important one: it is the *sandhi-split* word list
(`ca`, `eva`) while `english` is the *sandhi-joined* recited text (`caiva`).
Reconciling those two is what [`poc/sandhi_map.py`](poc/sandhi_map.py) does, and
it is what makes per-word audio and per-word meaning possible at all.

Two structural flaws in this file constrain everything downstream — repeated
words collapse because `synonyms` is a JSON object, and 19 of the 30
combined-verse entries have truncated `english`. Both are documented with
workarounds in [`poc/README.md`](poc/README.md#known-problems-in-gitajson).

### 3. Everything else is derived

Word/phrase/line timings, the synonym↔token mapping, quality flags and review
order are all generated — no manual timing except the two benchmark verses.
The full chain, the commands, and the measured accuracy are in
**[`poc/README.md`](poc/README.md)**.

```
BrajaBeats_Gita_MP3/ ─┐
                      ├─► forced alignment ─► word/phrase/line spans
gita.json ────────────┘        (poc/)         + sandhi-resolved meanings
```

---

Each recording contains the verse twice — once line-paced, then slowly
word-by-word with call-and-response echoes — over a continuous drone with no
silence anywhere. That single fact shapes every design decision in `poc/`.

## Credits

Audio: [BrajaBeats](https://www.youtube.com/@BrajaBeats). Text: Bhaktivedanta
translation and synonyms. Alignment: Meta MMS and the Vāgdhenu Sanskrit
Conformer — see [`poc/README.md`](poc/README.md#credits).
