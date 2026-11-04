"""Shloka learner app: serves poc/ (read-only) and a small student API. Standard library only.

    python app/server.py            # PORT env (default 8000), DB_PATH env (default app/students.db)

Students sign up with just a display name and get a private sign-in code (no e-mail, no password, no audio is stored).
The page keeps the code in the browser; typing it on another device gives the same progress.

  POST /api/students          {name}                -> {code, name}
  GET  /api/me                (X-Student-Code)      -> {name, state, progress}
  PUT  /api/me/state          {state}  (<=64 KB: marks, settings)
  POST /api/attempts          {verse, unit, idx, score, sound, pace, ratio, detail}
  GET  /api/attempts?verse=2.47                     -> this student's recent attempts
  GET  /api/teacher/students  (X-Teacher-Key = $TEACHER_KEY; disabled when unset) -> all students + summaries
  GET  /healthz
"""
import hashlib, hmac, json, os, re, secrets, sqlite3, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "poc")
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "students.db"))
TEACHER_KEY = os.environ.get("TEACHER_KEY", "")
MAX_BODY = 70 * 1024
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"          # no 0/O/1/I/L
STATIC_OK = {".html", ".js", ".css", ".json", ".mp3", ".png", ".ico", ".svg", ".txt"}
LOCK = threading.Lock()
HITS = {}                                              # ip -> [timestamps], for sign-up / bad-code throttling


def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT UNIQUE NOT NULL,
            created REAL NOT NULL, seen REAL NOT NULL, state TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
            verse TEXT NOT NULL, unit TEXT NOT NULL, idx INTEGER NOT NULL, score INTEGER, sound INTEGER, pace INTEGER,
            ratio REAL, detail TEXT, ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS att_student ON attempts(student_id, verse, ts);""")


def h(code):
    return hashlib.sha256(code.encode()).hexdigest()


def throttle(ip, kind, limit, per=3600):
    now = time.time()
    with LOCK:
        a = [t for t in HITS.get((ip, kind), []) if now - t < per]
        if len(a) >= limit:
            HITS[(ip, kind)] = a
            return False
        a.append(now)
        HITS[(ip, kind)] = a
        return True


def clean_name(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return re.sub(r"[<>]", "", s)[:40]


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def ip(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def student(self):
        code = (self.headers.get("X-Student-Code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{12,20}", code):
            return None
        if not throttle(self.ip(), "auth", 120, 600):
            return None
        with db() as c:
            r = c.execute("SELECT * FROM students WHERE code_hash=?", (h(code.replace("-", "")),)).fetchone()
            if r:
                c.execute("UPDATE students SET seen=? WHERE id=?", (time.time(), r["id"]))
        return r

    # ---- routing -------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/healthz":
            return self.send_json({"ok": True})
        if u.path.startswith("/api/"):
            return self.api("GET", u)
        if u.path == "/":
            self.send_response(302)
            self.send_header("Location", "/learn.html?src=tts")
            return self.end_headers()
        if os.path.splitext(u.path)[1].lower() not in STATIC_OK:
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if self.path.startswith("/api/") or os.path.splitext(urlparse(self.path).path)[1].lower() in STATIC_OK or self.path == "/healthz":
            return super().do_HEAD() if not self.path.startswith(("/api/", "/healthz")) else self.send_json({"ok": True})
        return self.send_error(404)

    def do_POST(self): self.api("POST", urlparse(self.path))
    def do_PUT(self): self.api("PUT", urlparse(self.path))

    def api(self, method, u):
        try:
            p = u.path
            if method == "POST" and p == "/api/students":
                if not throttle(self.ip(), "signup", 20):
                    return self.send_json({"error": "too many sign-ups from here, try later"}, 429)
                name = clean_name(self.body().get("name"))
                if not name:
                    return self.send_json({"error": "name required"}, 400)
                raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
                with db() as c:
                    c.execute("INSERT INTO students(name,code_hash,created,seen) VALUES(?,?,?,?)", (name, h(raw), time.time(), time.time()))
                return self.send_json({"name": name, "code": "-".join(raw[i:i + 4] for i in (0, 4, 8))}, 201)

            if p == "/api/teacher/students" and method == "GET":
                if not TEACHER_KEY or not hmac.compare_digest(self.headers.get("X-Teacher-Key", ""), TEACHER_KEY):
                    return self.send_json({"error": "forbidden"}, 403)
                with db() as c:
                    rows = c.execute("""SELECT s.id,s.name,s.created,s.seen,s.state,
                        (SELECT COUNT(*) FROM attempts a WHERE a.student_id=s.id) n,
                        (SELECT ROUND(AVG(score)) FROM attempts a WHERE a.student_id=s.id) avg,
                        (SELECT MAX(ts) FROM attempts a WHERE a.student_id=s.id) last
                        FROM students s ORDER BY s.seen DESC LIMIT 500""").fetchall()
                out = []
                for r in rows:
                    m = json.loads(r["state"] or "{}").get("marks", {})
                    out.append({"name": r["name"], "joined": r["created"], "seen": r["seen"], "attempts": r["n"], "avg_score": r["avg"],
                                "last_attempt": r["last"], "learned": sum(1 for v in m.values() if v.get("done")), "marked": sum(1 for v in m.values() if v.get("star"))})
                return self.send_json({"students": out})

            if not p.startswith("/api/me") and p != "/api/attempts":
                return self.send_json({"error": "not found"}, 404)
            s = self.student()
            if not s:
                return self.send_json({"error": "sign in"}, 401)

            if p == "/api/me" and method == "GET":
                with db() as c:
                    pr = c.execute("""SELECT verse, COUNT(*) n, MAX(score) best, CAST(ROUND(AVG(score)) AS INT) avg, MAX(ts) last
                        FROM attempts WHERE student_id=? GROUP BY verse""", (s["id"],)).fetchall()
                return self.send_json({"name": s["name"], "state": json.loads(s["state"] or "{}"), "progress": {r["verse"]: dict(r) for r in pr}})
            if p == "/api/me/state" and method == "PUT":
                st = self.body().get("state")
                if not isinstance(st, dict):
                    return self.send_json({"error": "state must be an object"}, 400)
                raw = json.dumps(st, separators=(",", ":"))
                if len(raw) > 65536:
                    return self.send_json({"error": "state too large"}, 413)
                with db() as c:
                    c.execute("UPDATE students SET state=? WHERE id=?", (raw, s["id"]))
                return self.send_json({"ok": True})
            if p == "/api/attempts" and method == "POST":
                b = self.body()
                verse, unit = str(b.get("verse", ""))[:12], str(b.get("unit", ""))[:8]
                if not re.fullmatch(r"\d{1,2}\.\d{1,3}(-\d{1,3})?", verse) or unit not in ("verse", "hemi", "pada", "word"):
                    return self.send_json({"error": "bad attempt"}, 400)
                det = json.dumps(b.get("detail") or {}, separators=(",", ":"))[:8000]
                num = lambda k, lo, hi: max(lo, min(hi, int(b.get(k) or 0)))
                with db() as c:
                    c.execute("INSERT INTO attempts(student_id,verse,unit,idx,score,sound,pace,ratio,detail,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (s["id"], verse, unit, num("idx", 0, 99), num("score", 0, 100), num("sound", 0, 100), num("pace", 0, 100),
                               round(float(b.get("ratio") or 0), 2), det, time.time()))
                return self.send_json({"ok": True}, 201)
            if p == "/api/attempts" and method == "GET":
                v = parse_qs(u.query).get("verse", [""])[0]
                with db() as c:
                    rows = c.execute("SELECT unit,idx,score,sound,pace,ratio,ts FROM attempts WHERE student_id=? AND verse=? ORDER BY ts DESC LIMIT 100", (s["id"], v)).fetchall()
                return self.send_json({"attempts": [dict(r) for r in rows]})
            return self.send_json({"error": "not found"}, 404)
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "bad request"}, 400)


if __name__ == "__main__":
    init()
    port = int(os.environ.get("PORT", "8000"))
    print(f"serving {ROOT} + API on :{port}, db {DB_PATH}, teacher view {'on' if TEACHER_KEY else 'off'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
