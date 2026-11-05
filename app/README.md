# Learner app: student accounts + chant feedback

`python app/server.py` serves `poc/` (read-only) and a small API (the docstring in `app/server.py` lists the routes). Standard library only.

* **Students**: a display name and a private sign-in code (no e-mail, no password). Marks, learned verses and practice scores sync across devices. No audio is uploaded.
* **Teacher view**: `/teacher.html`, protected by the `TEACHER_KEY` environment variable (off when unset).
* **Feedback** (`poc/feedback.js`, runs in the browser): in *Your turn* the mic records the learner, and the recording is lined up (DTW on speaker-normalised MFCCs) with the reference chant of that part. It gives a score, sound match, pace and per-word hints. The target must fit clearly better than the other parts of the same verse. It measures similarity of sound and rhythm, **not** correct phonemes.
* **Database on Cloudflare D1** (free tier, survives Render deploys):
  1. `npx wrangler login`, then `npx wrangler d1 create abhyasa` → note the `database_id`.
  2. Cloudflare dashboard → My Profile → API Tokens → Create token → permission *Account · D1 · Edit* → copy it.
  3. Note your Account ID (dashboard sidebar).
  4. In Render → the service → Environment: set `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_API_TOKEN`. The server creates its tables on start (`app/schema.sql` has the same SQL).
  The server talks to D1 over Cloudflare's REST API, so no Worker is needed; with the variables unset it uses local SQLite.
* **Deploy**: `render.yaml` (free plan, Singapore). Free disks are wiped on each deploy: attach a disk (paid) and set `DB_PATH` before real students use it.

## Better feedback later (researched)
| Option | Adds | Cost |
|---|---|---|
| MMS/wav2vec2 forced alignment of the recording (already used for the chant data) | per-word timing and confidence on the learner's own audio | needs torch; run on the GPU box, not the free web service |
| wav2vec2 phoneme recogniser (e.g. facebook/wav2vec2-lv-60-espeak-cv-ft, as in OpenPronounce / pronounce-assess) plus GOP/DTW against reference phonemes | real phoneme-level mispronunciation | ~350 MB model; server or Transformers.js |
| Teacher comments on a recording | human feedback, as on the Narottam app | needs audio storage |
