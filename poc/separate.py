"""Strip the tanpura/drone bed with Demucs, leaving the voice.

These recordings have a continuous musical bed -- `silencedetect` finds no
silence at all, even at -14 dB -- so both the energy splitter and the CTC
aligner are working through it. Separating the vocal stem first is independent
of which aligner you use.

Stems are cached as 16 kHz mono wav in poc/vocals/, keyed by source filename.

    .venv/bin/python separate.py --one "Bhagavad-gita 1.14.mp3"
    .venv/bin/python separate.py --all [limit]
"""
import os, sys, subprocess
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
BRAJA = os.path.join(REPO, "BrajaBeats_Gita_MP3")
CACHE = os.path.join(ROOT, "vocals")
SR = 16000

_model = None


def get_model():
    global _model
    if _model is None:
        from demucs.pretrained import get_model as load
        _model = load("htdemucs")
        _model.eval()
        if torch.cuda.is_available():
            _model.cuda()
    return _model


def cache_path(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    return os.path.join(CACHE, base + ".wav")


def decode_stereo(path, sr=44100):
    """Demucs wants 44.1 kHz stereo."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "2", "-ar", str(sr), "-"], capture_output=True, check=True)
    y = np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).T
    return np.ascontiguousarray(y)


def separate(filename, force=False):
    """Returns the path to the cached 16 kHz mono vocal stem."""
    out = cache_path(filename)
    if os.path.exists(out) and not force:
        return out
    os.makedirs(CACHE, exist_ok=True)

    from demucs.apply import apply_model
    model = get_model()
    wav = torch.from_numpy(decode_stereo(os.path.join(BRAJA, filename)))
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)
    with torch.inference_mode():
        stems = apply_model(model, wav[None],
                            device="cuda" if torch.cuda.is_available() else "cpu",
                            split=True, overlap=0.25, progress=False)[0]
    stems = stems * ref.std() + ref.mean()
    voc = stems[model.sources.index("vocals")].mean(0).cpu().numpy()

    # write 16 kHz mono wav via ffmpeg
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", "44100", "-ac", "1",
         "-i", "-", "-ar", str(SR), "-ac", "1", out], stdin=subprocess.PIPE)
    p.communicate(voc.astype(np.float32).tobytes())
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("ffmpeg failed writing " + out)
    return out


if __name__ == "__main__":
    a = sys.argv
    if "--one" in a:
        fn = a[a.index("--one") + 1]
        print(separate(fn, force="--force" in a))
    elif "--all" in a:
        i = a.index("--all")
        lim = int(a[i + 1]) if len(a) > i + 1 else None
        files = sorted(f for f in os.listdir(BRAJA) if f.lower().endswith(".mp3"))
        if lim:
            files = files[:lim]
        print(f"cuda: {torch.cuda.is_available()}   files: {len(files)}")
        for n, fn in enumerate(files, 1):
            try:
                separate(fn)
            except Exception as exc:
                print(f"  ! {fn}: {exc}")
            if n % 10 == 0:
                print(f"  … {n}/{len(files)}", flush=True)
        print("done ->", CACHE)
    else:
        print(__doc__)
