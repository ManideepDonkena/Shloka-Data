-- Cloudflare D1 schema (the server also creates these on start, so running this is optional)
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT UNIQUE NOT NULL,
  created REAL NOT NULL, seen REAL NOT NULL, state TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
  verse TEXT NOT NULL, unit TEXT NOT NULL, idx INTEGER NOT NULL, score INTEGER, sound INTEGER, pace INTEGER,
  ratio REAL, detail TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS att_student ON attempts(student_id, verse, ts);
