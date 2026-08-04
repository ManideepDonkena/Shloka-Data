"""Deterministic vocal-gap detection: ffmpeg + numpy only, no ML."""
import subprocess, sys, json
import numpy as np

SR = 16000
NFFT = 1024
HOP = 160          # 10 ms frames


def decode(path, sr=SR):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le",
         "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32)


def stft_mag(y, nfft=NFFT, hop=HOP):
    win = np.hanning(nfft).astype(np.float32)
    n = 1 + (len(y) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    frames = y[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1))


def voice_envelope(y, sr=SR):
    """dB envelope of the vocal band after subtracting the steady music bed."""
    S = stft_mag(y)                                   # (frames, bins)
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    band = (freqs >= 250) & (freqs <= 3800)

    # The tanpura/drone is stationary: its level per bin is well estimated by a
    # low percentile over time. Subtract it so only transient voice survives.
    floor = np.percentile(S, 20, axis=0, keepdims=True)
    resid = np.maximum(S - floor, 1e-8)

    env = np.sqrt((resid[:, band] ** 2).mean(axis=1))
    db = 20 * np.log10(env + 1e-8)

    # Spectral flux: voice changes fast, a drone does not.
    flux = np.sqrt(((np.diff(resid[:, band], axis=0, prepend=resid[:1, band])
                     .clip(min=0)) ** 2).mean(axis=1))
    fdb = 20 * np.log10(flux + 1e-8)
    return db, fdb


def smooth(x, k):
    if k <= 1:
        return x
    return np.convolve(x, np.ones(k) / k, mode="same")


def segments_from_mask(mask, hop_s, min_seg=0.30, min_gap=0.18):
    """Contiguous True runs -> (start, end) in seconds, with hysteresis cleanup."""
    m = mask.copy()
    # close short gaps
    runs = _runs(~m)
    for a, b in runs:
        if (b - a) * hop_s < min_gap:
            m[a:b] = True
    # drop short segments
    segs = []
    for a, b in _runs(m):
        if (b - a) * hop_s >= min_seg:
            segs.append((a * hop_s, b * hop_s))
    return segs


def _runs(mask):
    d = np.diff(mask.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts, ends))


def detect(path, pct=55.0, min_seg=0.30, min_gap=0.18):
    y = decode(path)
    db, fdb = voice_envelope(y)
    hop_s = HOP / SR
    score = smooth(db, 9) + 0.5 * smooth(fdb, 9)
    thr = np.percentile(score, pct)
    return segments_from_mask(score > thr, hop_s, min_seg, min_gap), len(y) / SR


if __name__ == "__main__":
    path = sys.argv[1]
    pct = float(sys.argv[2]) if len(sys.argv) > 2 else 55.0
    segs, dur = detect(path, pct)
    print(f"{path}  dur={dur:.2f}s  n_segments={len(segs)}")
    for i, (a, b) in enumerate(segs):
        print(f"  {i:2d}  {a:7.3f} -> {b:7.3f}   ({b-a:.3f}s)")
