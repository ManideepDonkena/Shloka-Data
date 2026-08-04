"""Tiny POC server: static files + a save endpoint so the Tag tab can write
data.json back to disk. Standard library only.

    python3 server.py [port]        # default 8765

Routes
    /                       index.html and friends (this folder)
    /braja/<file>.mp3       read-only passthrough to ../BrajaBeats_Gita_MP3
    GET  /api/audio         list of available source mp3s
    POST /api/save          body = the full data.json array; writes it out
                            (previous version kept in backups/)
"""
import json, os, re, shutil, sys, time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
BRAJA = os.path.join(REPO, "BrajaBeats_Gita_MP3")
BACKUPS = os.path.join(ROOT, "backups")
DATA = os.path.join(ROOT, "data.json")
MAX_BODY = 32 * 1024 * 1024


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in self.path or self.command == "POST":
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------- GET ----------
    def do_GET(self):
        if self.path.startswith("/api/audio"):
            try:
                files = sorted(f for f in os.listdir(BRAJA)
                               if f.lower().endswith((".mp3", ".wav", ".ogg")))
            except OSError:
                files = []
            return self._json({"files": files})

        if self.path.startswith("/braja/"):
            name = unquote(self.path[len("/braja/"):].split("?")[0])
            # keep it inside BRAJA
            target = os.path.normpath(os.path.join(BRAJA, name))
            if not target.startswith(os.path.abspath(BRAJA) + os.sep) or not os.path.isfile(target):
                self.send_error(404, "no such audio")
                return
            return self.serve_range(target, "audio/mpeg")

        # Media needs byte ranges or the browser cannot seek -- it restarts the
        # clip from 0. http.server ignores Range entirely, so handle it here.
        local = self.translate_path(self.path.split("?")[0])
        if os.path.isfile(local) and local.lower().endswith((".mp3", ".wav", ".ogg", ".m4a")):
            ctype = self.guess_type(local)
            return self.serve_range(local, ctype)

        return super().do_GET()

    # ---------- byte-range file serving ----------
    def serve_range(self, path, ctype):
        try:
            size = os.path.getsize(path)
        except OSError:
            return self.send_error(404, "not found")

        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)\s*$", rng.strip())
            if m:
                g1, g2 = m.group(1), m.group(2)
                if g1 == "" and g2 == "":
                    pass
                elif g1 == "":                      # suffix range: last N bytes
                    start, end = max(0, size - int(g2)), size - 1
                    partial = True
                else:
                    start = int(g1)
                    end = int(g2) if g2 else size - 1
                    partial = True
                end = min(end, size - 1)
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self):
        return self.do_GET()

    # ---------- POST ----------
    def do_POST(self):
        if not self.path.startswith("/api/save"):
            return self.send_error(404, "unknown endpoint")
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self._json({"ok": False, "error": "bad length"}, 400)
        if n <= 0 or n > MAX_BODY:
            return self._json({"ok": False, "error": "empty or oversized body"}, 400)

        raw = self.rfile.read(n)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return self._json({"ok": False, "error": f"invalid JSON: {exc}"}, 400)
        if not isinstance(payload, list) or not payload:
            return self._json({"ok": False, "error": "expected a non-empty array"}, 400)

        ok, why = validate(payload)
        if not ok:
            return self._json({"ok": False, "error": why}, 400)

        os.makedirs(BACKUPS, exist_ok=True)
        if os.path.exists(DATA):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(DATA, os.path.join(BACKUPS, f"data.{stamp}.json"))
        tmp = DATA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, DATA)

        nseg = sum(len(c["words"]) for v in payload
                   for l in v.get("lines", []) for c in l.get("chunks", []))
        return self._json({"ok": True, "verses": len(payload), "words": nseg,
                           "saved": time.strftime("%H:%M:%S")})


def validate(payload):
    """Cheap structural check so a UI bug can't shred the file."""
    for v in payload:
        if not isinstance(v, dict) or "id" not in v or "lines" not in v:
            return False, "verse missing id/lines"
        for L in v["lines"]:
            for span in (L.get("line_audio"),):
                if span and not _span_ok(span):
                    return False, f"{v['id']}: bad line span"
            for C in L.get("chunks", []):
                if not _span_ok(C.get("chunk_audio")):
                    return False, f"{v['id']}: bad phrase span"
                for w in C.get("words", []):
                    if not _span_ok(w.get("word_audio")):
                        return False, f"{v['id']}: bad word span on '{w.get('token')}'"
    return True, ""


def _span_ok(s):
    return (isinstance(s, dict) and isinstance(s.get("start"), (int, float))
            and isinstance(s.get("end"), (int, float))
            and s["end"] > s["start"] >= 0)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--lan"]
    port = int(args[0]) if args else 8765
    # Loopback by default: /api/save writes to disk, so this is not something
    # to expose casually. --lan opens it to the local network, which is how you
    # test the phone layout on a real phone.
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    srv = HTTPServer((host, port), Handler)
    print(f"Shloka POC  ->  http://localhost:{port}/   (ctrl-c to stop)")
    if host == "0.0.0.0":
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80)); lan = s.getsockname()[0]
        except OSError:
            lan = "<this machine's IP>"
        finally:
            s.close()
        print(f"  on your phone   ->  http://{lan}:{port}/   (same wi-fi)")
    print(f"  static  {ROOT}\n  audio   {BRAJA}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
