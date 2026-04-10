#!/usr/bin/env python3
"""
R2D2 Sound Codec (R2SC) — Real-time Synthesizer
================================================
Parses an R2SC codec string and synthesizes audio on-the-fly via FM synthesis.
No pre-generated .wav files required.

R2SC Grammar
------------
An utterance is a sequence of segments separated by " | ":

    W<f0>-<f1>:<fm>:<beta>:<dur>   Wobble with carrier sweep (most common)
    W<fc>:<fm>:<beta>:<dur>        Wobble at stable pitch
    S<f0>-<f1>:<dur>               Pure sweep (no FM)
    C<fc>:<dur>                    Chirp (pure tone, no FM)
    T<fc>:<fm>:<dur>               Trill (fast FM, beta=150 fixed)
    ~<dur>                         Silence

Parameter ranges (calibrated from real R2D2 reference sounds):
    fc / f0 / f1  : 150 - 3200  Hz
    fm            : 3 - 8       Hz  (wobble)  |  35 - 65 Hz  (trill)
    beta          : 20 - 150         (FM modulation depth)
    dur           : 0.05 - 4.0  s

Examples:
    "W1190-1364:8:21:0.42 | C681:0.07"         # acknowledged
    "W975-2278:4:76:0.65"                        # surprised
    "W585-945:3:136:1.01"                        # worried
    "C1344:0.27 | W1131-1359:3:42:0.41"         # curious
    "W1008-1796:4:85:2.05"                       # concerned
    "S520-1750:0.20 | C1600:0.08"               # affirmative
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from typing import List

import numpy as np

SAMPLE_RATE = 44100
AMPLITUDE   = 0.75   # global output level (0..1)


# ---------------------------------------------------------------------------
# Cross-platform audio playback
# ---------------------------------------------------------------------------

def _play_wav_file(path: str, alsa_device: str = "plughw:1,0") -> None:
    """Play a .wav file. Uses aplay on Linux, afplay on macOS."""
    if sys.platform == "darwin":
        subprocess.run(["afplay", path], check=False)
    else:
        subprocess.run(["aplay", "-q", "-D", alsa_device, path], check=False)


# ---------------------------------------------------------------------------
# Segment data classes
# ---------------------------------------------------------------------------

@dataclass
class SegW:
    """Wobble: FM synthesis + optional carrier sweep."""
    f0: float          # carrier start Hz
    f1: float          # carrier end Hz  (== f0 if stable)
    fm: float          # modulator Hz
    beta: float        # modulation index
    dur: float         # seconds

@dataclass
class SegS:
    """Pure sweep."""
    f0: float
    f1: float
    dur: float

@dataclass
class SegC:
    """Chirp / pure tone."""
    fc: float
    dur: float

@dataclass
class SegT:
    """Trill (fast FM, fixed beta=150)."""
    fc: float
    fm: float
    dur: float

@dataclass
class SegSilence:
    dur: float


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_RE_W2  = re.compile(r'^W(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')
_RE_W1  = re.compile(r'^W(\d+(?:\.\d+)?):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')
_RE_S   = re.compile(r'^S(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')
_RE_C   = re.compile(r'^C(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')
_RE_T   = re.compile(r'^T(\d+(?:\.\d+)?):(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$')
_RE_SIL = re.compile(r'^~(\d+(?:\.\d+)?)$')


def parse(codec: str) -> List:
    """Parse R2SC string -> list of segment objects."""
    segments = []
    for tok in codec.split("|"):
        tok = tok.strip()
        if not tok:
            continue

        m = _RE_W2.match(tok)
        if m:
            segments.append(SegW(float(m[1]), float(m[2]), float(m[3]), float(m[4]), float(m[5])))
            continue

        m = _RE_W1.match(tok)
        if m:
            fc = float(m[1])
            segments.append(SegW(fc, fc, float(m[2]), float(m[3]), float(m[4])))
            continue

        m = _RE_S.match(tok)
        if m:
            segments.append(SegS(float(m[1]), float(m[2]), float(m[3])))
            continue

        m = _RE_C.match(tok)
        if m:
            segments.append(SegC(float(m[1]), float(m[2])))
            continue

        m = _RE_T.match(tok)
        if m:
            segments.append(SegT(float(m[1]), float(m[2]), float(m[3])))
            continue

        m = _RE_SIL.match(tok)
        if m:
            segments.append(SegSilence(float(m[1])))
            continue

        raise ValueError(f"Cannot parse R2SC segment: '{tok}'")

    return segments


# ---------------------------------------------------------------------------
# Synthesis engine
# ---------------------------------------------------------------------------

def _envelope(n: int, attack_s: float, release_s: float, sr: int) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    a = min(int(attack_s * sr), n // 2)
    r = min(int(release_s * sr), n // 2)
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    if r > 0:
        env[-r:] = np.linspace(1.0, 0.0, r)
    return env


def _synth_segment(seg, sr: int) -> np.ndarray:
    if isinstance(seg, SegSilence):
        return np.zeros(int(seg.dur * sr), dtype=np.float32)

    n = int(seg.dur * sr)
    t = np.arange(n, dtype=np.float64) / sr

    if isinstance(seg, SegW):
        fc_t = np.linspace(seg.f0, seg.f1, n)
        carrier_phase = 2.0 * np.pi * np.cumsum(fc_t) / sr
        fm_phase = seg.beta * np.sin(2.0 * np.pi * seg.fm * t)
        signal = np.sin(carrier_phase + fm_phase)
        attack = min(0.015, seg.dur * 0.05)
        release = min(0.040, seg.dur * 0.10)
        signal *= _envelope(n, attack, release, sr)

    elif isinstance(seg, SegS):
        fc_t = np.linspace(seg.f0, seg.f1, n)
        carrier_phase = 2.0 * np.pi * np.cumsum(fc_t) / sr
        signal = np.sin(carrier_phase)
        signal *= _envelope(n, 0.010, 0.020, sr)

    elif isinstance(seg, SegC):
        carrier_phase = 2.0 * np.pi * seg.fc * t
        signal = np.sin(carrier_phase)
        signal *= _envelope(n, 0.005, 0.020, sr)

    elif isinstance(seg, SegT):
        carrier_phase = 2.0 * np.pi * seg.fc * t
        fm_phase = 150.0 * np.sin(2.0 * np.pi * seg.fm * t)
        signal = np.sin(carrier_phase + fm_phase)
        signal *= _envelope(n, 0.010, 0.030, sr)

    else:
        return np.zeros(n, dtype=np.float32)

    return (AMPLITUDE * signal).astype(np.float32)


def synthesize(codec: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Parse an R2SC codec string and return a numpy float32 audio array.
    Raises ValueError for unparseable tokens.
    """
    segments = parse(codec)
    parts = [_synth_segment(s, sr) for s in segments]
    if not parts:
        return np.zeros(int(0.1 * sr), dtype=np.float32)
    return np.concatenate(parts)


def to_wav_bytes(codec: str, sr: int = SAMPLE_RATE) -> bytes:
    """Synthesize and return raw WAV bytes."""
    samples = synthesize(codec, sr)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_int16 = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_int16.tobytes())
    return buf.getvalue()


def save_wav(codec: str, path: str, sr: int = SAMPLE_RATE) -> None:
    """Synthesize and save to a .wav file."""
    with open(path, "wb") as f:
        f.write(to_wav_bytes(codec, sr))


def play(codec: str, alsa_device: str = "plughw:1,0") -> None:
    """Synthesize and play immediately. Cross-platform."""
    wav = to_wav_bytes(codec)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
        tmp = f.name
    try:
        _play_wav_file(tmp, alsa_device)
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="R2SC Synthesizer")
    parser.add_argument("codec", nargs="?", help="R2SC string to synthesize and play")
    parser.add_argument("--out", help="Save to .wav file instead of playing")
    parser.add_argument("--device", default="plughw:1,0", help="ALSA device (Linux only)")
    parser.add_argument("--demo", action="store_true", help="Play all reference examples")
    args = parser.parse_args()

    EXAMPLES = [
        ("acknowledged",  "W1190-1364:8:21:0.42 | C681:0.07"),
        ("surprised",     "W975-2278:4:76:0.65"),
        ("worried",       "W585-945:3:136:1.01"),
        ("curious",       "C1344:0.27 | W1131-1359:3:42:0.41"),
        ("concerned",     "W1008-1796:4:85:2.05"),
        ("excited",       "W1300-2167:5:96:0.93"),
        ("chat",          "W1953-2476:4:27:1.02"),
        ("excited (big)", "W1300-1531:4:126:1.99"),
    ]

    if args.demo:
        platform = "macOS (afplay)" if sys.platform == "darwin" else "Linux (aplay)"
        print(f"R2SC Demo  [{platform}]\n")
        for label, codec_str in EXAMPLES:
            print(f"  {label:<20}  {codec_str}")
            play(codec_str, args.device)
            time.sleep(0.3)

    elif args.codec:
        if args.out:
            save_wav(args.codec, args.out)
            print(f"Saved: {args.out}")
        else:
            play(args.codec, args.device)

    else:
        parser.print_help()
