# Vāgdhenu-chanted Gītā with word-by-word synonyms

Replaces the "split the BrajaBeats mp3" step: [Vāgdhenu](https://github.com/prathoshap/vagdhenu) chants each
half-verse as its own clip, so line boundaries are exact by construction; words are then aligned with MMS and
joined to `poc/mapping.json` synonyms.

1. `scripts/build_shards.py ../gita.json shard.json --verses 2.20,18.66` — one render clip per half-verse
2. Render with Vāgdhenu's `src/render.py` (needs a GPU; on Blackwell use torch cu128, not the pinned cu121)
3. `scripts/assemble_align.py` — joins clips (0.55 s gap), aligns words, writes `web/verses/<c.v>.{wav,json}`
4. `web/index.html` — word cards with meanings; tap to play a word, gold card follows the chant.
   Serve with `python3 -m http.server` inside `web/`.

Status: 3 verses (1.14, 2.20, 18.66) rendered. Audio quality not yet reviewed by ear.
Known issues: words split across a line break (e.g. kadācin in 2.20) spill over the boundary; very short spans
(mā in 18.66); every verse rendered as anuṣṭubh (triṣṭubh verses need meter detection); merged verses skipped.
Scripts contain absolute paths from the dev machine — adjust before reuse.
