"""Chant scorer: checks a learner's recording against the words it should contain, with the MMS forced-alignment model
(the same model the chant data was aligned with). Needs torch + torchaudio (a GPU is used when present).

    SCORER_KEY=some-secret python app/scorer.py          # PORT env, default 8765

POST /score  (header X-Scorer-Key)  {"words": ["karmaṇy", "evādhikāras", "te"], "audio": "<base64 16 kHz mono int16>"}
  -> {"ok": true, "score": 0-100, "heard": bool, "words": [{"token", "lp", "verdict": "good"|"check"|"missed"}]}
GET  /healthz

How it scores: the model gives, every 20 ms, a probability for each letter. The expected words are forced-aligned to the
recording and each word gets the mean log-probability of its letters (lp). Calibrated on 30 BrajaBeats verses (a human
chanter) against the TTS text: correct words median -0.85 (5% below -2.2), a wrong word put in its place median -6.1,
room noise -4.6. So lp >= -2.3 is "good", down to -3.5 "check", below that "missed". The part's score maps mean lp
-4 .. -1 to 0 .. 100. It checks the sounds (letters), not pitch or melody.
"""
import base64, hmac, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import torch
import torchaudio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "poc"))
from align_mms import load_model, romanize  # noqa: E402

KEY = os.environ.get("SCORER_KEY", "")
GOOD, CHECK = -2.3, -3.5
LOCK = threading.Lock()                         # one GPU, one alignment at a time


def score(words, pcm):
    bundle, model, tok, _ = load_model()
    dev = next(model.parameters()).device
    x = torch.tensor(pcm, dtype=torch.float32)[None].to(dev)
    with LOCK, torch.inference_mode():
        em, _ = model(x)
        em = torch.log_softmax(em, -1)[0]
    rom = [romanize(w) for w in words]
    keep = [i for i, r in enumerate(rom) if r]
    toks = tok([rom[i] for i in keep])
    flat = [t for w in toks for t in w]
    if not flat or em.shape[0] < len(flat):
        return {"ok": True, "heard": False, "score": 0, "words": [{"token": w, "lp": None, "verdict": "missed"} for w in words]}
    al, sc = torchaudio.functional.forced_align(em[None], torch.tensor([flat], device=em.device), blank=0)
    spans = torchaudio.functional.merge_tokens(al[0], sc[0].exp())
    out, k, lps = [{"token": w, "lp": None, "verdict": "missed"} for w in words], 0, []
    for wi, t in zip(keep, toks):
        s = spans[k:k + len(t)]
        k += len(t)
        lp = float(np.mean([np.log(max(z.score, 1e-6)) for z in s]))
        lps.append(lp)
        out[wi].update(lp=round(lp, 2), verdict="good" if lp >= GOOD else "check" if lp >= CHECK else "missed")
    m = float(np.mean(lps))
    return {"ok": True, "heard": m > -4.0, "score": int(max(0, min(100, round((m + 4) / 3 * 100)))), "words": out}


class H(BaseHTTPRequestHandler):
    def send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self.send({"ok": True, "model": "MMS_FA"} if self.path == "/healthz" else {"error": "not found"}, 200 if self.path == "/healthz" else 404)

    def do_POST(self):
        if self.path != "/score":
            return self.send({"error": "not found"}, 404)
        if KEY and not hmac.compare_digest(self.headers.get("X-Scorer-Key", ""), KEY):
            return self.send({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 3_000_000:
            return self.send({"error": "too large"}, 413)
        try:
            b = json.loads(self.rfile.read(n))
            words = [str(w) for w in b["words"]][:40]
            pcm = np.frombuffer(base64.b64decode(b["audio"]), dtype="<i2").astype(np.float32) / 32768.0
            if not 0.3 * 16000 <= len(pcm) <= 30 * 16000:
                return self.send({"error": "audio must be 0.3 to 30 s"}, 400)
            return self.send(score(words, pcm))
        except (KeyError, ValueError, TypeError) as e:
            return self.send({"error": "bad request: %s" % e}, 400)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    load_model()
    port = int(os.environ.get("PORT", "8765"))
    print(f"scorer on :{port} ({'key required' if KEY else 'NO KEY: local use only'})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
