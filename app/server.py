"""Shloka learner app: serves poc/ (read-only) and a small student API. Standard library only.

    python app/server.py            # PORT env (default 8000); storage: Cloudflare D1 if CF_ACCOUNT_ID, CF_D1_DATABASE_ID and
                                    # CF_API_TOKEN are set, else SQLite at DB_PATH (default app/students.db)

Students sign up with just a display name and get a private sign-in code (no e-mail, no password, no audio is stored).
The page keeps the code in the browser; typing it on another device gives the same progress.

  POST /api/students          {name}                -> {code, name}
  GET  /api/me                (X-Student-Code)      -> {name, state, progress}
  PUT  /api/me/state          {state}  (<=64 KB: marks, settings)
  POST /api/attempts          {verse, unit, idx, score, sound, pace, ratio, detail}
  GET  /api/attempts?verse=2.47                     -> this student's recent attempts
  GET  /api/teacher/students  (X-Teacher-Key = $TEACHER_KEY; disabled when unset) -> all students + summaries
  GET  /api/verses            -> {ready, verses:[{id,chapter,shloka}]}   (ready=false while the database is being filled)
  GET  /api/verses/<id>       -> the full verse (words, timings, meanings, translation, purport)
  GET  /healthz
"""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, sys, threading, time, urllib.request, urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "poc")
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "students.db"))
TEACHER_KEY = os.environ.get("TEACHER_KEY", "")
MAX_BODY = 70 * 1024
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"          # no 0/O/1/I/L
STATIC_OK = {".html", ".js", ".css", ".json", ".mp3", ".png", ".ico", ".svg", ".txt"}
SCORER_URL = os.environ.get("SCORER_URL", "").rstrip("/")   # app/scorer.py (MMS model) running on a GPU machine
SCORER_KEY = os.environ.get("SCORER_KEY", "")
CORS_EXTRA = tuple(x for x in os.environ.get("CORS_ORIGINS", "").split(",") if x)   # extra allowed origins (testing)
LOCK = threading.Lock()
HITS = {}                                              # ip -> [timestamps], for sign-up / bad-code throttling


# ---- storage: Cloudflare D1 (over its REST API) when CF_* are set, otherwise a local SQLite file -------------------------
CF_ACCOUNT, CF_DB, CF_TOKEN = (os.environ.get(k, "") for k in ("CF_ACCOUNT_ID", "CF_D1_DATABASE_ID", "CF_API_TOKEN"))
CF_BASE = os.environ.get("CF_API_BASE", "https://api.cloudflare.com/client/v4")
USE_D1 = bool(CF_ACCOUNT and CF_DB and CF_TOKEN)
_missing = [k for k, v in (("CF_ACCOUNT_ID", CF_ACCOUNT), ("CF_D1_DATABASE_ID", CF_DB), ("CF_API_TOKEN", CF_TOKEN)) if not v]
if _missing and len(_missing) < 3:
    sys.stderr.write("WARNING: Cloudflare D1 NOT used, these variables are empty or missing: %s\n" % ", ".join(_missing))


class DbError(Exception):
    pass


def q(sql, params=()):
    """Run one statement, return rows as dicts (empty list for writes)."""
    if USE_D1:
        req = urllib.request.Request(
            f"{CF_BASE}/accounts/{CF_ACCOUNT}/d1/database/{CF_DB}/query",
            data=json.dumps({"sql": sql, "params": list(params)}).encode(), method="POST",
            headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                body = json.load(e)
                why = "; ".join("%s %s" % (x.get("code"), x.get("message")) for x in body.get("errors", []))[:300]
            except Exception:
                why = ""
            raise DbError("HTTP %s from Cloudflare%s" % (e.code, (": " + why) if why else ""))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise DbError(str(e))
        if not j.get("success"):
            raise DbError(json.dumps(j.get("errors"))[:300])
        res = j.get("result") or [{}]
        return res[0].get("results") or []
    c = sqlite3.connect(DB_PATH, timeout=10)
    try:
        c.row_factory = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}
        rows = c.execute(sql, tuple(params)).fetchall()
        c.commit()
        return rows
    finally:
        c.close()


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT UNIQUE NOT NULL,
        created REAL NOT NULL, seen REAL NOT NULL, state TEXT NOT NULL DEFAULT '{}')""",
    """CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
        verse TEXT NOT NULL, unit TEXT NOT NULL, idx INTEGER NOT NULL, score INTEGER, sound INTEGER, pace INTEGER,
        ratio REAL, detail TEXT, ts REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS att_student ON attempts(student_id, verse, ts)",
    "CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, student_id INTEGER NOT NULL, created REAL NOT NULL)",
    """CREATE TABLE IF NOT EXISTS verses(id TEXT PRIMARY KEY, chapter INTEGER NOT NULL, shloka TEXT NOT NULL, ord INTEGER NOT NULL,
        h TEXT NOT NULL, data TEXT NOT NULL, purport TEXT NOT NULL DEFAULT '')""",
]


# ---- verses: poc/tts_data.json + poc/purports.json are loaded into the database (re-seeded when a verse changes) -------
VSTATE = {"total": 0, "done": 0, "ready": False, "error": ""}
VCACHE = {}          # id -> JSON string of the full verse (the content only changes on a re-seed)
VINDEX = {"t": 0, "body": None}


def seed_verses():
    try:
        data = json.load(open(os.path.join(ROOT, "tts_data.json"), encoding="utf-8"))
        try:
            pur = json.load(open(os.path.join(ROOT, "purports.json"), encoding="utf-8"))
        except OSError:
            pur = {}
        VSTATE["total"] = len(data)
        have = {r["id"]: r["h"] for r in q("SELECT id, h FROM verses")}
        VSTATE["done"] = 0
        for i, v in enumerate(data):
            body = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            pp = pur.get(v["id"], "")
            hh = hashlib.sha1((body + "|" + pp).encode()).hexdigest()
            if have.get(v["id"]) != hh:
                q("INSERT OR REPLACE INTO verses(id,chapter,shloka,ord,h,data,purport) VALUES(?,?,?,?,?,?,?)",
                  (v["id"], int(v["chapter"]), str(v["shloka"]), i, hh, body, pp))
                VCACHE.pop(v["id"], None)
            VSTATE["done"] += 1
        VINDEX["body"] = None
        VSTATE["ready"] = True
        sys.stderr.write("verses ready: %d in the database\n" % len(data))
    except Exception as e:                      # the site keeps working from the static files if this fails
        VSTATE["error"] = str(e)[:200]
        sys.stderr.write("verse seeding failed: %s\n" % e)
        return False
    return True


def seed_loop():
    while not seed_verses():
        time.sleep(60)
        try:
            ensure_db()
        except DbError:
            pass



DBSTATE = {"ok": False, "error": "", "tried": 0.0}


def init():
    if not USE_D1:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    for st in SCHEMA:
        q(st)
    for col in ("username TEXT", "pw TEXT"):                      # accounts added later: add the columns to an existing table
        try:
            q("ALTER TABLE students ADD COLUMN " + col)
        except Exception as e:
            if "duplicate" not in str(e).lower() and "exists" not in str(e).lower():
                raise
    q("CREATE UNIQUE INDEX IF NOT EXISTS students_username ON students(username)")
    DBSTATE.update(ok=True, error="")


def ensure_db():
    """Create the tables once the database answers. Retries at most every 20 s, so a wrong key does not take the site down."""
    if DBSTATE["ok"]:
        return
    if time.time() - DBSTATE["tried"] < 20:
        raise DbError(DBSTATE["error"] or "database not ready")
    DBSTATE["tried"] = time.time()
    try:
        init()
    except DbError as e:
        DBSTATE["error"] = str(e)
        sys.stderr.write("database unavailable: %s (check CF_ACCOUNT_ID, CF_D1_DATABASE_ID, CF_API_TOKEN: token needs Account > D1 > Edit)\n" % e)
        raise


USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,29}$")
ROUNDS = 200_000


def hash_password(password):                  # same scheme as lesson-board: PBKDF2-SHA256, per-user salt
    salt = secrets.token_bytes(16)
    d = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS)
    return "pbkdf2$%d$%s$%s" % (ROUNDS, base64.b64encode(salt).decode(), base64.b64encode(d).decode())


def verify_password(password, stored):
    try:
        _, rounds, salt, digest = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(got, base64.b64decode(digest))
    except (ValueError, TypeError, AttributeError):
        return False


def new_token(student_id):
    raw = "".join(secrets.choice(ALPHABET) for _ in range(28))
    q("INSERT INTO sessions(token_hash, student_id, created) VALUES(?,?,?)", (h(raw), student_id, time.time()))
    return raw


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

    CORS_OK = ("https://localhost", "http://localhost", "capacitor://localhost")

    def cors(self):
        pass                                        # kept for older call sites; headers are added once in end_headers()

    def end_headers(self):
        o = self.headers.get("Origin", "")
        if o and (o in self.CORS_OK or o in CORS_EXTRA):   # the Android app (Capacitor) loads the API and audio from its own origin
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Student-Code, X-Teacher-Key")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.cors()
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
        if not re.fullmatch(r"[A-Z0-9-]{12,40}", code):
            return None
        if not throttle(self.ip(), "auth", 120, 600):
            return None
        key = h(code.replace("-", ""))
        rows = q("SELECT s.* FROM sessions t JOIN students s ON s.id=t.student_id WHERE t.token_hash=?", (key,))   # a sign-in session
        if not rows:
            rows = q("SELECT * FROM students WHERE code_hash=?", (key,))                                          # an older guest code
        r = rows[0] if rows else None
        if r and time.time() - r["seen"] > 300:          # one write per 5 min is plenty (fewer D1 round trips)
            q("UPDATE students SET seen=? WHERE id=?", (time.time(), r["id"]))
        return r

    # ---- routing -------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/healthz":
            return self.send_json({"ok": True, "storage": "d1" if USE_D1 else "sqlite", "db": {"ok": DBSTATE["ok"], "error": DBSTATE["error"]}, "scorer": bool(SCORER_URL), "cf_vars_present": {"CF_ACCOUNT_ID": bool(CF_ACCOUNT), "CF_D1_DATABASE_ID": bool(CF_DB), "CF_API_TOKEN": bool(CF_TOKEN)}})
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
                q("INSERT INTO students(name,code_hash,created,seen) VALUES(?,?,?,?)", (name, h(raw), time.time(), time.time()))
                return self.send_json({"name": name, "code": "-".join(raw[i:i + 4] for i in (0, 4, 8))}, 201)

            if method == "POST" and p == "/api/score":                 # forwarded to the MMS scorer; the browser falls back if it is off
                if not SCORER_URL:
                    return self.send_json({"error": "scorer off"}, 503)
                if not throttle(self.ip(), "score", 120, 600):
                    return self.send_json({"error": "too many attempts, wait a few minutes"}, 429)
                n = int(self.headers.get("Content-Length") or 0)
                if n > 2_000_000:
                    return self.send_json({"error": "recording too long"}, 413)
                req = urllib.request.Request(SCORER_URL + "/score", data=self.rfile.read(n), method="POST",
                                             headers={"Content-Type": "application/json", "X-Scorer-Key": SCORER_KEY})
                try:
                    with urllib.request.urlopen(req, timeout=25) as r:
                        return self.send_json(json.load(r))
                except (urllib.error.URLError, OSError, ValueError) as e:
                    sys.stderr.write("scorer unreachable: %s\n" % e)
                    return self.send_json({"error": "scorer unreachable"}, 503)
            if p.startswith("/api/") and p not in ("/api/verses",) and not p.startswith("/api/verses/"):
                ensure_db()
            if method == "GET" and p == "/api/verses":
                if not VSTATE["ready"]:
                    return self.send_json({"ready": False, "done": VSTATE["done"], "total": VSTATE["total"], "error": VSTATE["error"]})
                if VINDEX["body"] is None or time.time() - VINDEX["t"] > 600:
                    rows = q("SELECT id, chapter, shloka FROM verses ORDER BY ord")
                    VINDEX["body"], VINDEX["t"] = rows, time.time()
                return self.send_json({"ready": True, "verses": VINDEX["body"]})
            if method == "GET" and p.startswith("/api/verses/"):
                vid = p[len("/api/verses/"):]
                if not re.fullmatch(r"\d{1,2}\.\d{1,3}(-\d{1,3})?", vid):
                    return self.send_json({"error": "bad id"}, 400)
                if vid not in VCACHE:
                    rows = q("SELECT data, purport FROM verses WHERE id=?", (vid,))
                    if not rows:
                        return self.send_json({"error": "not found"}, 404)
                    d = json.loads(rows[0]["data"])
                    d["purport"] = rows[0]["purport"]
                    VCACHE[vid] = json.dumps(d, ensure_ascii=False)
                b = VCACHE[vid].encode()
                self.send_response(200)
                self.cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(b)
                return

            if method == "POST" and p == "/api/auth/register":
                if not throttle(self.ip(), "signup", 20):
                    return self.send_json({"error": "too many sign-ups from here, try later"}, 429)
                b = self.body()
                user = str(b.get("username", "")).strip().lower()
                pw = str(b.get("password", ""))
                if not USERNAME.match(user):
                    return self.send_json({"error": "Usernames are 3 to 30 characters: letters, numbers, dots, dashes or underscores."}, 400)
                if not 6 <= len(pw) <= 200:
                    return self.send_json({"error": "Choose a password of at least 6 characters."}, 400)
                if q("SELECT 1 FROM students WHERE username=?", (user,)):
                    return self.send_json({"error": "That username is taken."}, 409)
                name = clean_name(b.get("name")) or user
                dummy = h("".join(secrets.choice(ALPHABET) for _ in range(12)))     # the old code column stays unique and unused
                q("INSERT INTO students(name,code_hash,created,seen,username,pw) VALUES(?,?,?,?,?,?)",
                  (name, dummy, time.time(), time.time(), user, hash_password(pw)))
                sid = q("SELECT id FROM students WHERE username=?", (user,))[0]["id"]
                return self.send_json({"name": name, "username": user, "code": new_token(sid)}, 201)
            if method == "POST" and p == "/api/auth/login":
                ip = self.ip()
                with LOCK:
                    fails = [t for t in HITS.get((ip, "loginfail"), []) if time.time() - t < 600]
                    HITS[(ip, "loginfail")] = fails
                if len(fails) >= 10:
                    return self.send_json({"error": "Too many wrong passwords from here. Try again in a few minutes."}, 429)
                b = self.body()
                rows = q("SELECT id, name, username, pw FROM students WHERE username=?", (str(b.get("username", "")).strip().lower(),))
                if not rows or not rows[0]["pw"] or not verify_password(str(b.get("password", "")), rows[0]["pw"]):
                    with LOCK:
                        HITS.setdefault((ip, "loginfail"), []).append(time.time())      # only wrong passwords count
                    return self.send_json({"error": "Wrong username or password."}, 401)
                r = rows[0]
                return self.send_json({"name": r["name"], "username": r["username"], "code": new_token(r["id"])})
            if method == "POST" and p == "/api/auth/claim":              # a guest adds a username and password to keep the account
                s = self.student()
                if not s:
                    return self.send_json({"error": "sign in"}, 401)
                if s.get("username"):
                    return self.send_json({"error": "This account already has a username."}, 400)
                b = self.body()
                user = str(b.get("username", "")).strip().lower()
                pw = str(b.get("password", ""))
                if not USERNAME.match(user):
                    return self.send_json({"error": "Usernames are 3 to 30 characters: letters, numbers, dots, dashes or underscores."}, 400)
                if not 6 <= len(pw) <= 200:
                    return self.send_json({"error": "Choose a password of at least 6 characters."}, 400)
                if q("SELECT 1 FROM students WHERE username=?", (user,)):
                    return self.send_json({"error": "That username is taken."}, 409)
                q("UPDATE students SET username=?, pw=? WHERE id=?", (user, hash_password(pw), s["id"]))
                return self.send_json({"ok": True, "username": user})
            if method == "POST" and p == "/api/auth/delete":             # the learner deletes their account and everything in it
                s = self.student()
                if not s:
                    return self.send_json({"error": "sign in"}, 401)
                for sql in ("DELETE FROM attempts WHERE student_id=?", "DELETE FROM sessions WHERE student_id=?", "DELETE FROM students WHERE id=?"):
                    q(sql, (s["id"],))
                return self.send_json({"ok": True})
            if method == "POST" and p == "/api/auth/logout":
                code = (self.headers.get("X-Student-Code") or "").strip().upper().replace("-", "")
                if code:
                    q("DELETE FROM sessions WHERE token_hash=?", (h(code),))
                return self.send_json({"ok": True})

            if p == "/api/teacher/students" and method == "GET":
                if not TEACHER_KEY:
                    return self.send_json({"error": "teacher view is off: set TEACHER_KEY in the server's environment"}, 503)
                if not hmac.compare_digest(self.headers.get("X-Teacher-Key", ""), TEACHER_KEY):
                    return self.send_json({"error": "wrong teacher key"}, 403)
                rows = q("""SELECT s.id,s.name,s.username,s.created,s.seen,s.state,
                    (SELECT COUNT(*) FROM attempts a WHERE a.student_id=s.id) n,
                    (SELECT ROUND(AVG(score)) FROM attempts a WHERE a.student_id=s.id) avg,
                    (SELECT MAX(ts) FROM attempts a WHERE a.student_id=s.id) last
                    FROM students s ORDER BY s.seen DESC LIMIT 500""")
                out = []
                for r in rows:
                    m = json.loads(r["state"] or "{}").get("marks", {})
                    out.append({"name": r["name"], "username": r.get("username") or "", "joined": r["created"], "seen": r["seen"], "attempts": r["n"], "avg_score": r["avg"],
                                "last_attempt": r["last"], "learned": sum(1 for v in m.values() if v.get("done")), "marked": sum(1 for v in m.values() if v.get("star"))})
                return self.send_json({"students": out, "storage": "d1" if USE_D1 else "sqlite"})

            if not p.startswith("/api/me") and p != "/api/attempts":
                return self.send_json({"error": "not found"}, 404)
            s = self.student()
            if not s:
                return self.send_json({"error": "sign in"}, 401)

            if p == "/api/me" and method == "GET":
                pr = q("""SELECT verse, COUNT(*) n, MAX(score) best, CAST(ROUND(AVG(score)) AS INT) avg, MAX(ts) last
                    FROM attempts WHERE student_id=? GROUP BY verse""", (s["id"],))
                return self.send_json({"name": s["name"], "username": s.get("username") or "", "state": json.loads(s["state"] or "{}"), "progress": {r["verse"]: r for r in pr}})
            if p == "/api/me/state" and method == "PUT":
                st = self.body().get("state")
                if not isinstance(st, dict):
                    return self.send_json({"error": "state must be an object"}, 400)
                raw = json.dumps(st, separators=(",", ":"))
                if len(raw) > 65536:
                    return self.send_json({"error": "state too large"}, 413)
                q("UPDATE students SET state=? WHERE id=?", (raw, s["id"]))
                return self.send_json({"ok": True})
            if p == "/api/attempts" and method == "POST":
                b = self.body()
                verse, unit = str(b.get("verse", ""))[:12], str(b.get("unit", ""))[:8]
                if not re.fullmatch(r"\d{1,2}\.\d{1,3}(-\d{1,3})?", verse) or unit not in ("verse", "hemi", "pada", "word"):
                    return self.send_json({"error": "bad attempt"}, 400)
                det = json.dumps(b.get("detail") or {}, separators=(",", ":"))[:8000]
                num = lambda k, lo, hi: max(lo, min(hi, int(b.get(k) or 0)))
                q("INSERT INTO attempts(student_id,verse,unit,idx,score,sound,pace,ratio,detail,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (s["id"], verse, unit, num("idx", 0, 99), num("score", 0, 100), num("sound", 0, 100), num("pace", 0, 100),
                   round(float(b.get("ratio") or 0), 2), det, time.time()))
                return self.send_json({"ok": True}, 201)
            if p == "/api/attempts" and method == "GET":
                v = parse_qs(u.query).get("verse", [""])[0]
                rows = q("SELECT unit,idx,score,sound,pace,ratio,ts FROM attempts WHERE student_id=? AND verse=? ORDER BY ts DESC LIMIT 100", (s["id"], v))
                return self.send_json({"attempts": rows})
            return self.send_json({"error": "not found"}, 404)
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "bad request"}, 400)
        except DbError as e:
            sys.stderr.write("database error: %s\n" % e)
            return self.send_json({"error": "database unavailable, try again"}, 503)


if __name__ == "__main__":
    try:
        ensure_db()
    except DbError:
        pass                                    # keep serving; every API call retries (see /healthz "db")
    threading.Thread(target=seed_loop, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"serving {ROOT} + API on :{port}, db {'Cloudflare D1' if USE_D1 else DB_PATH}, teacher view {'on' if TEACHER_KEY else 'off'}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
