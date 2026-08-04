# Shloka — Bhagavad-gītā verse memorization POC

Turns each BrajaBeats recitation into a nested, clickable structure so a learner
can hear any level of the verse and see what it means.

```
verse
  line          × N
    phrase      × 2   (at the metrical caesura)
      word      × k   + sandhi-resolved synonym + meaning
```

**Live:** `https://<user>.github.io/Shloka-Data/poc/`
**Local:** `python3 server.py` → http://localhost:8765

---

## The recordings

Established by measurement, not assumption:

- Each file contains the verse **twice** — a line-paced recitation, then a slow
  word-by-word pass with **call-and-response echoes** (a word span and the "gap"
  after it fingerprint at cos 0.37–0.65 vs a 0.18 baseline: it's the same word
  repeated).
- There is **no silence anywhere**. `silencedetect` finds nothing at −14 dB
  against the continuous tanpura bed, so energy thresholding cannot segment it.
- Lines split into **exactly 2 phrases** at the caesura, in every verse checked.

Word and phrase audio therefore come from the slow pass; line and verse audio
from the recitation pass. One file per verse serves every level.

---

## Results

**Sandhi mapping** (`sandhi_map.py`) — maps sandhi-split `synonyms` keys onto
sandhi-joined verse tokens by folding to a skeleton and aligning with a monotonic
many-to-many DP, then a second pass that re-matches uncertain groups against the
whole list. Handles `śvetaiḥ→śvetair`, `pāṇḍavaḥ→pāṇḍavaś`, `ca + eva → caiva`,
avagraha (`’haṁ` = `aham`), and compounds split across the dict
(`bhīmābhirakṣitam ← bhīma + abhirakṣitam`).

> **99.0%** of the 627 single-verse entries align cleanly (median cost 0.081).
> Corpus-wide: 572 clean / 79 weak / 6 failed.

**Alignment** — line-boundary error against the two hand-tagged verses:

| method | 1.14 | 18.66 |
|---|---|---|
| DSP energy valleys | 490 ms | 512 ms |
| MMS CTC + valley snap | 390 ms | 437 ms |
| Sushrota CTC + valley snap | 390 ms | 437 ms |

**The two aligners agree with each other far more tightly than either agrees
with the hand tags.** Across 3,054 boundaries: median difference **0 ms**,
76% within 50 ms, 80% within 100 ms. MMS (multilingual wav2vec2, roman chars)
and Sushrota (Sanskrit Conformer, Devanagari BPE) share no architecture, training
data or tokenizer — so where they converge the boundary is very likely right,
and the residual ~400 ms is the *hand tags* being loose, not the models.

That cross-check drives the review order: fix what the models disagree about.
About 14 verses disagree by 20–30 s (one aligner locked onto the second pass);
95 verses agree on ≥90% of boundaries and mostly just need accepting.

**Confidence alone is not a quality signal.** An 18.8 s `sarvam` scored 0.76.
`flag_spans.py` adds an independent check — Sanskrit is near-isochronous per
syllable, so a word should last ≈ syllables × the verse's median s/syllable.
10.8% of MMS spans fail it. Verses where the aligners agree average 2.63 suspect
spans; where they diverge, 5.56 — two unrelated signals corroborating.

**Demucs was tested and rejected.** Vocal separation changed suspect-span counts
not at all (0/13 and 1/12 either way) and *lowered* CTC confidence on both
verses. The drone is not the bottleneck. Kept behind `align_mms.py --vocals`.

---

## Files

| | |
|---|---|
| `index.html` | the whole app — Study / Recite / Mapping QA / Tag editor |
| `server.py` | static + **byte ranges** (media cannot seek without them) + `/api/save` |
| `sandhi_map.py` | synonym ↔ verse token mapping |
| `build_mapping.py` → `mapping.json` | that mapping for all 657 verses, for QA |
| `build_data.py` → `data.json` | **the verified set** |
| `auto_split.py` → `auto_data.json` | DSP splitter, count-constrained by the text |
| `align_mms.py` → `aligned_data.json` | MMS forced alignment + valley snap |
| `align_sushrota.py` → `sushrota_data.json` | Sanskrit Conformer alignment |
| `consensus.py` → `consensus.json` | cross-aligner agreement, drives review order |
| `flag_spans.py` | flags implausible spans, adds `review_score` |
| `separate.py` | Demucs vocal stem (optional) |
| `domstub.js` | `node domstub.js` — smoke test, catches load-time errors |

## Tabs

- **Study** — clickable words, live highlighting, translation, meanings
- **Recite** — teacher drill: settle → chant → breath → *cue* → your turn → rest,
  with pace control, cumulative build-up, progressive word → phrase → line → verse
- **Mapping QA** — sandhi/synonym mapping for all 657 verses, weakest first
- **Tag editor** — waveform, draggable START/END handles, audition either
  boundary zoomed, accept-as-verified, save

Playback plays the **exact** tagged span; lead-in and tail are scheduled
*silence*, never neighbouring audio (median inter-word gap is only ~160 ms).

## Rebuilding

```bash
python3 build_mapping.py            # 657-verse mapping QA
python3 build_data.py               # verified set
python3 auto_split.py --all         # DSP baseline

python3 -m venv .venv --system-site-packages
.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv/bin/python align_mms.py --eval     # score against hand tags
.venv/bin/python align_mms.py --all      # ~2 min on GPU, ~37 min on CPU
python3 flag_spans.py aligned_data.json
python3 consensus.py
```

Sushrota needs its own env (NeMo pins its own torch):

```bash
python3 -m venv .venv-nemo
.venv-nemo/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv-nemo/bin/pip install "nemo_toolkit[asr]" indic-transliteration
.venv-nemo/bin/python align_sushrota.py --all
```

Stock NeMo cannot load that checkpoint. `align_sushrota.py` works around three
things: the tokenizer is typed `multilingual` where NeMo branches on `agg`; the
RNNT decoder takes `multisoftmax` from AI4Bharat's fork; and the CTC head is
shared across 22 languages, so log-probs are taken over the Sanskrit slice plus
blank (offset 4096, verified against the tokenizer's own vocabulary) rather than
all 5,632 classes. Only preprocessor → ConformerEncoder → CTC head is built.

---

## Saving edits

`data.json` is the **verified** set. Model output lives separately and a verse is
copied across only once you touch or accept it, so saving never dumps unreviewed
guesses into the curated file.

| | needs | writes |
|---|---|---|
| **Save to disk** | `server.py` | `poc/data.json` + backup in `poc/backups/` |
| **Commit to GitHub** | fine-grained PAT | `poc/data.json` as a real commit |
| **Download copy** | nothing | your Downloads |

Spans are validated (`end > start ≥ 0`) and written temp-then-rename.

## Deploying

GitHub Pages serves the repo directly, audio included (339 MB, largest file
1.4 MB). Settings → Pages → deploy from `main`, root. The app detects it is not
running under `server.py` and loads audio from `../BrajaBeats_Gita_MP3/`.

To tag from the hosted site, open **Tag editor → GitHub settings** once: repo,
branch, path `poc/data.json`, and a **fine-grained** token scoped to this one
repository with *Contents: read and write*. It lives in `localStorage` and goes
only to api.github.com — use a short expiry and **Forget token** on shared
machines. Every save becomes a commit, so a bad session is one `git revert` away.

No free host gives a durable writable disk (Render/Railway sleep and wipe, HF
Spaces resets on rebuild) — hence the GitHub-commit path: the repo is the store.

---

## Known problems in `gita.json`

1. `synonyms` is a JSON **object**, so a word repeated in a verse survives only
   once — BG 9.16 has `aham` five times, one entry. Worked around by a reuse edge
   in the aligner; the real fix is re-scraping synonyms as an ordered list.
2. **19 of the 30 combined-verse entries have truncated `english`** — only the
   first verse, while `synonyms` covers the whole group (14.22-25: 47 synonyms,
   16 tokens). Those 28 audio files cannot be tagged until re-scraped.

## Known limits

- The benchmark is **two loosely hand-tagged verses**, one of which claims a line
  starts at 0.00 s when the voice starts at 2.04 s. Every accuracy figure above is
  measured against that. Tightening a handful of verses would tell us more than
  another model would.
- Word-level tags are model output, not verified. ~70% of verses have at least
  one span worth a nudge.
- 3.2% of adjacent word pairs sit under 50 ms apart — no detectable pause, so
  that cut is guesswork. Shown in the Tag editor's `gap` column.

## Credits

Audio: BrajaBeats. Text: `gita.json` (Bhaktivedanta translation/synonyms).
Aligners: Meta [MMS](https://pytorch.org/audio/stable/generated/torchaudio.pipelines.MMS_FA.html)
· [`prathoshap/sushrota-sanskrit-asr`](https://huggingface.co/prathoshap/sushrota-sanskrit-asr)
(IndicConformer, from the [Vāgdhenu](https://prathosh.in/vagdhenu/) project).
