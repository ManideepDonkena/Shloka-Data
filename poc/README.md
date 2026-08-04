# Shloka — Bhagavad-gītā verse memorization POC

Turns each BrajaBeats recitation into a nested, clickable structure so a learner
can hear any level of the verse and see what it means.

```
verse
  line          × N
    phrase      × 2   (at the metrical caesura)
      word      × k   + sandhi-resolved synonym + meaning
```

**Live:** `https://manideepdonkena.github.io/Shloka-Data/poc/`
**Local:** `python3 server.py` → http://localhost:8765

Works on a phone: the transport and tabs stay pinned while you scroll, the
waveform pinch-zooms, and every control is a real touch target.

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

## How each artifact is produced

Only two inputs are external — the mp3s and `gita.json`, both described in the
[root README](../README.md#where-each-artifact-came-from). Everything below is
generated, and every box is one script you can re-run.

```
   ../BrajaBeats_Gita_MP3/           ../gita.json
   Bhagavad-gita 2.20.mp3            657 verses: Devanagari, IAST,
            │                        synonyms{}, translation, purport
            │      join on re.search(r"(\d+)\.(\d+)", filename)
            └──────────────┬───────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
   TEXT SIDE                             AUDIO SIDE
   sandhi_map.py                         align_mms.py      → aligned_data.json
   fold to skeleton, monotonic DP,       align_sushrota.py → sushrota_data.json
   repair pass, refine pass              auto_split.py     → auto_data.json
        │                                     │
   build_mapping.py → mapping.json       flag_spans.py  (adds suspect / review_score)
   (QA for all 657)                      consensus.py   → consensus.json
        │                                     │
        └──────────────────┬──────────────────┘
                           │
                    index.html  ── you correct spans in the Tag editor ──┐
                           │                                             │
                    build_data.py ────────────────► data.json ◄──────────┘
                    (from the 2 hand-tagged           THE VERIFIED SET
                     benchmark verses)
```

### Text side — where the words and meanings come from

`gita.json` gives sandhi-**split** dictionary keys (`ca`, `eva`) but the verse is
recited sandhi-**joined** (`caiva`). Neither the audio nor the meanings can be
attached per word until those two are reconciled.

[`sandhi_map.py`](sandhi_map.py) does it deterministically, no model involved:

1. **Fold** both sides to a diacritic-free skeleton — `ā→a`, `ṛ→r`, `ś/ṣ→s`,
   `ṇ→n`, `ṁ→m`, `ḥ→h` — plus an avagraha rule so `’haṁ` reads as `aham`.
2. **Align** the two sequences with a monotonic many-to-many DP whose edit cost
   has a single-character sandhi floor: one letter of difference between two
   words of length ≥2 costs at most 0.15, because that is what sandhi *is*
   (`śvetaiḥ→śvetair`, `pāṇḍavaḥ→pāṇḍavaś`). A REPEAT edge lets one dictionary
   key serve two tokens, working around the collapsed-duplicates bug below.
3. **Repair** — a second pass re-matches any group costing ≥0.35 against the
   whole synonym list, not just its neighbours. This is what fixes compounds
   split across the dictionary (`bhīmābhirakṣitam ← bhīma + abhirakṣitam`).
4. **Refine** — split an n:n group into 1:1 pairs when the per-pair costs say
   the DP merged them only for convenience.

> **99.0%** of the 627 single-verse entries align cleanly (median cost 0.081).
> Corpus-wide: 572 clean / 79 weak / 6 failed.

`build_mapping.py` runs this over all 657 verses into `mapping.json`, which is
what the **Mapping QA** tab reads. Every token there shows the synonym it was
matched to, its cost, and whether the repair pass moved it (`✎`) or a key was
reused (`↺`).

### Audio side — where the timings come from

There is no silence to cut on, so segmentation is **forced alignment**: given
the audio *and* the known text, place each character in time. This is a Viterbi
path through a CTC lattice — deterministic, not speech recognition, and it
cannot invent words that aren't in the verse.

- [`align_mms.py`](align_mms.py) — Meta's MMS aligner (multilingual wav2vec2,
  roman characters) via `torchaudio.functional.forced_align`. The verse is
  wrapped in `*` star tokens so the intro music and the entire second recitation
  pass are absorbed rather than dragging the alignment out of shape. Boundaries
  are then **snapped** onto the nearest energy valley in a 300–3500 Hz vocal
  envelope, which cuts line error from 490 ms to 390 ms.
- [`align_sushrota.py`](align_sushrota.py) — the Vāgdhenu Sanskrit Conformer
  (Devanagari BPE), as a genuinely independent second opinion.
- [`auto_split.py`](auto_split.py) — the pure-DSP baseline: valley search
  constrained by the token count from the text side, candidate splits scored
  against syllable-count expectations. No model, useful as a control.
- [`flag_spans.py`](flag_spans.py) — Sanskrit is near-isochronous per syllable,
  so a word should last ≈ syllables × the verse's median s/syllable. Spans far
  off that get `suspect`, `dur_ratio` and `review_score`.
- [`consensus.py`](consensus.py) — compares the two aligners against each other
  and writes `consensus.json`, which sets the review order.

---

## Results

**Alignment** — line-boundary error against the two hand-tagged verses:

| method | 1.14 | 18.66 |
|---|---|---|
| DSP energy valleys | 490 ms | 512 ms |
| MMS CTC + valley snap | 390 ms | 437 ms |
| Sushrota CTC + valley snap | 390 ms | 437 ms |

**The two aligners agree with each other far more tightly than either agrees
with the hand tags.** Across 3,054 boundaries: median difference **0 ms**,
76% within 50 ms, 80% within 100 ms. MMS and Sushrota share no architecture,
training data or tokenizer — so where they converge the boundary is very likely
right, and the residual ~400 ms is the *hand tags* being loose, not the models.

That cross-check drives the review order: fix what the models disagree about.
About 14 verses disagree by 20–30 s (one aligner locked onto the second pass);
95 verses agree on ≥90% of boundaries and mostly just need accepting.

**Confidence alone is not a quality signal.** An 18.8 s `sarvam` scored 0.76.
The duration check is the independent one: 10.8% of MMS spans fail it. Verses
where the aligners agree average 2.63 suspect spans; where they diverge, 5.56 —
two unrelated signals corroborating.

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
| `gapdetect.py` | ffmpeg decode + spectral helpers, shared by every script |
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

---

## Run it locally

### Just to use or tag (no models, no GPU)

```bash
git clone https://github.com/ManideepDonkena/Shloka-Data.git
cd Shloka-Data/poc
python3 server.py            # http://localhost:8765
```

Standard library only. `server.py` exists rather than `python3 -m http.server`
for two reasons: it serves **HTTP byte ranges**, without which the browser
cannot seek media, and it exposes `POST /api/save` so the Tag editor can write
`data.json` back to disk with a backup.

All the generated JSON is committed, so the app is fully usable immediately —
you only need what follows if you want to *regenerate* it.

### To regenerate the text-side artifacts (no models either)

```bash
python3 build_mapping.py            # → mapping.json, the 657-verse QA view
python3 build_data.py               # → data.json from the hand-tagged verses
python3 auto_split.py --all         # → auto_data.json, the DSP baseline
```

`build_data.py` and `auto_split.py` need `numpy` and `ffmpeg` on `PATH`.

### To regenerate the alignments (needs torch)

```bash
python3 -m venv .venv --system-site-packages
.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv/bin/python align_mms.py --eval     # score against the hand-tagged verses
.venv/bin/python align_mms.py --one 2 47 # one verse, verbose
.venv/bin/python align_mms.py --all      # ~2 min on GPU, ~37 min on CPU
python3 flag_spans.py aligned_data.json
python3 consensus.py
```

Drop the `--index-url` for a CPU-only install; set `ALIGN_DEVICE=cpu` to force
CPU on a machine that has CUDA. GPU and CPU output was verified byte-identical.

Sushrota needs its own environment, because NeMo pins its own torch:

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

After editing `index.html`, run the smoke test — `node --check` only parses, and
a temporal-dead-zone error killed the whole page once:

```bash
node domstub.js        # → "LOADED OK"
```

---

## How to improve it

The models are done improving on their own; what the project needs now is a
larger verified benchmark. The fastest path from "258 machine guesses" to
"trustworthy data" is:

1. **Start the server** and open the **Tag editor**. Leave `source` on
   `+ MMS forced alignment` and set `order` to **worst first** — that sorts by
   cross-aligner disagreement, which is the only ground-truth-free quality
   signal available, so you spend your attention where it pays.
2. **Work down the segment table.** Rows highlighted amber have an implausible
   duration; a `gap` under 50 ms means there is no detectable pause between two
   words, so that cut is guesswork worth checking.
3. **Fix boundaries only.** Click a row, then *▶ hear start* / *▶ hear end* — it
   plays a short window straddling that one cut and zooms the waveform to it, so
   you judge by ear rather than by eye. Nudge ±20/±100 ms, drag the handle on the
   waveform, or drag a selection and press *⇤ from selection*.
   Keyboard: `←`/`→` nudge start (hold `alt` for end, `shift` for 100 ms),
   `[`/`]` audition, `j`/`k` step segments.
4. **Accept verses the models already got right** with *✓ Accept verse as
   verified* — no pointless nudge needed. Verses where the aligners agree ≥90%
   usually just need this.
5. **Save.** `data.json` is the *verified* set; a machine-tagged verse is copied
   into it only once you touch or accept it, so saving never dumps unreviewed
   guesses into the curated file.
6. **Re-measure.** With more verified verses, `align_mms.py --eval` becomes a
   real benchmark instead of a two-verse anecdote, and the numbers in *Results*
   above can be replaced with something defensible.

Text-side problems are a different fix: the **Mapping QA** tab with the filter on
*Needs review* shows exactly which synonym↔token pairs the DP got wrong. Those
are corrected in [`sandhi_map.py`](sandhi_map.py) — an extra rule in `fold()` or
`cost()` — never by hand-editing the output, so the fix generalises. Re-run
`build_mapping.py` and the clean/weak/failed counts tell you whether the rule
actually helped.

---

## Saving edits

| | needs | writes |
|---|---|---|
| **Save to disk** | `server.py` | `poc/data.json` + backup in `poc/backups/` |
| **Commit to GitHub** | fine-grained PAT | `poc/data.json` as a real commit |
| **Download copy** | nothing | your Downloads |

Spans are validated (`end > start ≥ 0`) and written temp-then-rename.

## Deploying

GitHub Pages serves the repo directly, audio included (337 MB over 286 files,
largest 1.4 MB — well inside the 1 GB soft limit). Settings → Pages → deploy
from `main`, root. The app detects it is not running under `server.py` and loads
audio from `../BrajaBeats_Gita_MP3/`, percent-encoding the `#` that 54 of the
filenames still carry.

To tag from the hosted site, open **Tag editor → GitHub settings** once: repo,
branch, path `poc/data.json`, and a **fine-grained** token scoped to this one
repository with *Contents: read and write*. It lives in `localStorage` and goes
only to api.github.com — use a short expiry and **Forget token** on shared
machines. Every save becomes a commit, so a bad session is one `git revert` away.
If you are not the repo owner, fork it first and point the token at your fork.

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
