# What we can add and improve

## Learning
- Spaced repetition: resurface learned verses after 1, 3, 7, 21 days; a "today" list.
- Recall mode with real checking: hide words, learner chants, feedback scores it (today it only hides text).
- Per-verse goals and streaks; chapter and overall progress screen; certificates for a finished chapter.
- Verse-quest style levels (Words → Pādas → Halves → Verse) that unlock one after another.
- Compare two verses that share words; show the sandhi split ("kadācana", "’stv") as a tap-to-explain.
- Short Prabhupāda purport summary beside the full text; word-by-word glossary search.

## Audio
- Listen to the hardest parts: render a slower Vāgdhenu take (0.8) for natural slow speed instead of stretching.
- Triṣṭubh / jagatī meter detection (all verses currently use anuṣṭubh/upajāti/vaṃśastha by syllable count).
- Listen-through of a whole chapter as a playlist; offline caching of the MP3s (service worker).
- Choose a voice (male/female reference) once more references exist.
- Hand-check the 6 low-confidence verses (4.31, 2.56, 2.24, 7.20, 12.10, 2.7) and the ~30 merged verses.

## Feedback
- Phoneme-level scoring (wav2vec2 phoneme model + GOP) on a GPU/paid server; forced alignment of the learner's recording with MMS.
- Teacher comments and optional audio submission (needs storage + consent for minors).
- Tune thresholds using real learner recordings; per-voice calibration (a different voice currently costs points).
- Show the learner's pitch/pace curve over the reference.

## Students and teachers
- Persistent database (Render disk or free external Postgres); passwords or teacher-issued codes; password-protected sign-in recovery.
- Teacher: classes, assignments ("learn BG 2.47–2.50 by Friday"), per-student drill-down, CSV export.
- Privacy: data-deletion button, minimal retention, privacy notice.

## App and quality
- Installable PWA (works offline), better phone layout and haptics, dark-mode polish.
- Accessibility: screen-reader labels, keyboard shortcuts help, high-contrast option.
- Automated tests for the player (sequencing/highlight) and feedback engine; CI check on PRs.
- Remove the dev-machine absolute paths from tts/scripts; document the full re-render steps.
- Repo size: move the 51 MB of audio to release assets or object storage.
- Other texts: Śrīmad-Bhāgavatam verses, Īśopaniṣad, Bhaja Govindam using the same pipeline.
