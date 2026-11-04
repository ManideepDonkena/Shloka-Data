# Vāgdhenu-chanted Gītā with word-by-word synonyms

Replaces the "split the BrajaBeats mp3" step: [Vāgdhenu](https://github.com/prathoshap/vagdhenu) chants each
half-verse as its own clip, so line boundaries are exact by construction; words are then aligned with MMS and
joined to `poc/mapping.json` synonyms.

1. `scripts/build_shards.py ../gita.json shard.json --verses 2.20,18.66` — one render clip per half-verse
2. Render with Vāgdhenu's `src/render.py` (needs a GPU; on Blackwell use torch cu128, not the pinned cu121)
3. `scripts/assemble_align.py` — joins clips (0.55 s gap), aligns words, writes `web/verses/<c.v>.{wav,json}`
4. `web/index.html` — word cards with meanings; tap to play a word, gold card follows the chant.
   Serve with `python3 -m http.server` inside `web/`.

Status: all 657 verses rendered and aligned (`poc/tts_data.json`, `poc/audio-tts/*.mp3`, ~51 MB at 56 kbps).
Alignment confidence per verse: median 0.91, minimum 0.74 (6 verses under 0.80). Audio not yet reviewed by ear.

How the full set was made (see `scripts/`):
- `build_shards.py --all` - one render clip per half-verse (a half ends at a danda); meter chosen from the syllable count
  (16 anuṣṭubh, 22-23 upajāti, 24 vaṃśastha). Speaker lines ("X uvāca", also fused "śrībhagavānuvāca") are not chanted.
- Render with Vāgdhenu's `src/render.py`; `assemble_align.py` joins clips, aligns words with MMS, writes MP3 + `tts_data.json`.
  Each word runs to the next word's onset (the chant is legato, so a word's tail rings into the gap).
- `fix_merged.py` - `poc/mapping.json` has no usable word list for the 30 merged verses (1.16-18 ...) and 6.24 (gita.json's
  transliteration only covers the first verse / two lines). Their words are rebuilt from the Devanagari, so these
  verses have coarser, sandhi-joined words (some compounds run 3-5 s) but still carry meanings.

Known issues: word boundaries are aligner-based, not hand-checked; merged verses (30) and 6.24 have coarse words;
scripts contain absolute paths from the dev machine.
