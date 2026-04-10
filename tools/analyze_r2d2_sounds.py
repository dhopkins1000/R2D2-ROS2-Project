#!/usr/bin/env python3
"""
R2D2 Sound Analyzer
====================
Analyzes original R2D2 MP3 files and extracts acoustic parameters
that can be used to design the R2D2 Sound Codec (R2SC).

For each sound file the script extracts:
  - Overall duration and RMS amplitude
  - Temporal segmentation into discrete events (silence-separated)
  - Per-event: dominant frequency, frequency trajectory (sweep up/down/stable),
    FM modulation rate and depth, attack/release times
  - A human-readable summary and a machine-readable JSON output

Usage
-----
    # Install dependencies (run once)
    pip install librosa numpy scipy soundfile matplotlib

    # Analyze all MP3s in r2d2_sounds/
    python3 tools/analyze_r2d2_sounds.py --sounds_dir r2d2_sounds/

    # Analyze a single file
    python3 tools/analyze_r2d2_sounds.py --file r2d2_sounds/excited.mp3

    # Also produce spectrogram plots
    python3 tools/analyze_r2d2_sounds.py --sounds_dir r2d2_sounds/ --plot

Output
------
    analysis/                    <- created next to sounds_dir
        excited.json             <- per-file parameter JSON
        excited_spectrogram.png  <- optional spectrogram
        summary.json             <- all files combined
"""

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import scipy.signal as signal

try:
    import librosa
    import librosa.display
except ImportError:
    raise SystemExit("librosa not found. Run: pip install librosa")

try:
    import matplotlib
    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EventParams:
    """Acoustic parameters for one discrete sound event."""
    index: int
    start_s: float
    end_s: float
    duration_ms: float

    # Pitch / frequency
    freq_start_hz: float       # dominant freq at event start
    freq_end_hz: float         # dominant freq at event end
    freq_mean_hz: float        # mean dominant freq
    freq_trajectory: str       # "up", "down", "stable", "complex"
    freq_range_hz: float       # max - min within event

    # FM modulation
    fm_rate_hz: float          # estimated modulation frequency (0 = none)
    fm_depth: float            # normalised modulation depth 0..1
    fm_character: str          # "none", "vibrato", "wobble", "trill", "buzz"

    # Amplitude envelope
    attack_ms: float
    release_ms: float
    peak_amplitude: float      # 0..1


@dataclass
class SoundAnalysis:
    """Full analysis result for one MP3 file."""
    filename: str
    emotion_label: str         # derived from filename
    duration_s: float
    sample_rate: int
    rms_amplitude: float
    event_count: int
    events: List[EventParams]
    suggested_codec: str       # human-readable R2SC sketch


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

SILENCE_THRESHOLD_DB = -40
MIN_EVENT_DURATION_S = 0.03


def _load(path: str):
    """Load audio file, return (samples_float32, sample_rate)."""
    y, sr = librosa.load(path, sr=None, mono=True)
    return y.astype(np.float32), sr


def _detect_events(y: np.ndarray, sr: int):
    """
    Split audio into discrete non-silent events.
    Returns list of (start_sample, end_sample) tuples.
    """
    intervals = librosa.effects.split(
        y,
        top_db=-SILENCE_THRESHOLD_DB,
        frame_length=512,
        hop_length=128,
    )
    # Merge very short gaps
    merged = []
    for iv in intervals:
        if merged and (iv[0] - merged[-1][1]) / sr < 0.05:
            merged[-1] = (merged[-1][0], iv[1])
        else:
            merged.append(list(iv))
    # Filter very short events
    return [
        (s, e) for s, e in merged
        if (e - s) / sr >= MIN_EVENT_DURATION_S
    ]


def _dominant_freq_track(y: np.ndarray, sr: int, hop: int = 128):
    """
    Returns array of dominant frequencies per frame using autocorrelation pitch tracker.
    Frames where no clear pitch found return np.nan.
    """
    f0, voiced, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C3"),   # ~130 Hz
        fmax=librosa.note_to_hz("C8"),   # ~4186 Hz
        sr=sr,
        hop_length=hop,
    )
    return f0  # shape (n_frames,), nan where unvoiced


def _fm_analysis(f0_track: np.ndarray, sr: int, hop: int = 128):
    """
    Estimate FM modulation rate and depth from a frequency track.
    Returns (rate_hz, depth_normalised, character_str).
    """
    valid = f0_track[~np.isnan(f0_track)]
    if len(valid) < 8:
        return 0.0, 0.0, "none"

    # Depth = std/mean of frequency track
    depth = float(np.std(valid) / (np.mean(valid) + 1e-6))

    # Rate: FFT of the frequency track itself
    frame_rate = sr / hop
    detrended = valid - np.mean(valid)
    freqs = np.fft.rfftfreq(len(detrended), d=1.0 / frame_rate)
    power = np.abs(np.fft.rfft(detrended)) ** 2
    # Look in 3-80 Hz range (below 3 Hz is just pitch drift)
    mask = (freqs >= 3) & (freqs <= 80)
    if not np.any(mask):
        return 0.0, depth, "none"
    peak_idx = np.argmax(power[mask])
    rate = float(freqs[mask][peak_idx])

    # Classify
    if depth < 0.02:
        character = "none"
    elif rate < 12:
        character = "vibrato" if depth < 0.08 else "wobble"
    elif rate < 35:
        character = "wobble"
    elif rate < 65:
        character = "trill"
    else:
        character = "buzz"

    return rate, min(depth, 1.0), character


def _envelope_times(y: np.ndarray, sr: int):
    """Estimate attack and release times in ms."""
    env = np.abs(y)
    peak_idx = int(np.argmax(env))
    peak_val = env[peak_idx]
    threshold = 0.1 * peak_val

    # Attack: first sample that crosses 10% of peak
    attack_idx = 0
    for i in range(peak_idx):
        if env[i] >= threshold:
            attack_idx = i
            break
    attack_ms = (peak_idx - attack_idx) / sr * 1000

    # Release: last sample above 10% of peak
    release_idx = len(env) - 1
    for i in range(len(env) - 1, peak_idx, -1):
        if env[i] >= threshold:
            release_idx = i
            break
    release_ms = (release_idx - peak_idx) / sr * 1000

    return float(attack_ms), float(release_ms)


def _freq_trajectory(f0_start, f0_end, f0_range):
    ratio = f0_end / (f0_start + 1e-6)
    if f0_range > 300:
        if ratio > 1.25:
            return "up"
        elif ratio < 0.75:
            return "down"
        else:
            return "complex"
    elif ratio > 1.15:
        return "up"
    elif ratio < 0.85:
        return "down"
    else:
        return "stable"


def _codec_sketch(events: List[EventParams]) -> str:
    """
    Generate a rough R2SC codec string from extracted events.
    Format per segment:
      C<freq>:<dur>        chirp (stable, no FM)
      S<f0>-<f1>:<dur>     sweep
      W<freq>:fm<rate>:b<depth*200>:<dur>   wobble/trill
      B<freq>:<dur>        buzz
    All freqs in Hz (rounded), durations in seconds (2 decimal places).
    """
    parts = []
    for ev in events:
        dur = f"{ev.duration_ms / 1000:.2f}"
        fc = int(round(ev.freq_mean_hz))
        if ev.fm_character in ("trill", "buzz", "wobble"):
            beta = int(round(ev.fm_depth * 200))
            rate = int(round(ev.fm_rate_hz))
            prefix = "T" if ev.fm_character == "trill" else ("B" if ev.fm_character == "buzz" else "W")
            parts.append(f"{prefix}{fc}:fm{rate}:b{beta}:{dur}")
        elif ev.freq_trajectory in ("up", "down"):
            f0 = int(round(ev.freq_start_hz))
            f1 = int(round(ev.freq_end_hz))
            parts.append(f"S{f0}-{f1}:{dur}")
        else:
            parts.append(f"C{fc}:{dur}")
    return " | ".join(parts)


def analyze_file(path: str) -> SoundAnalysis:
    """Full analysis pipeline for one audio file."""
    path = Path(path)
    label = path.stem.lower().replace(" ", "_").replace("-", "_")

    y, sr = _load(str(path))
    duration = len(y) / sr
    rms = float(np.sqrt(np.mean(y ** 2)))

    event_intervals = _detect_events(y, sr)
    hop = 128

    events = []
    for i, (s, e) in enumerate(event_intervals):
        chunk = y[s:e]
        f0_track = _dominant_freq_track(chunk, sr, hop)
        valid_f0 = f0_track[~np.isnan(f0_track)]

        if len(valid_f0) == 0:
            # No clear pitch — probably noise/buzz, use spectral centroid
            centroid = librosa.feature.spectral_centroid(y=chunk, sr=sr, hop_length=hop)
            valid_f0 = centroid[0][centroid[0] > 0]

        if len(valid_f0) == 0:
            continue

        freq_start = float(np.nanmean(f0_track[:max(1, len(f0_track) // 6)]))
        freq_end = float(np.nanmean(f0_track[max(0, -len(f0_track) // 6):]))
        freq_mean = float(np.nanmean(f0_track))
        freq_range = float(np.nanmax(valid_f0) - np.nanmin(valid_f0))

        fm_rate, fm_depth, fm_char = _fm_analysis(f0_track, sr, hop)
        attack_ms, release_ms = _envelope_times(chunk, sr)
        peak_amp = float(np.max(np.abs(chunk)))

        traj = _freq_trajectory(freq_start, freq_end, freq_range)

        events.append(EventParams(
            index=i,
            start_s=round(s / sr, 3),
            end_s=round(e / sr, 3),
            duration_ms=round((e - s) / sr * 1000, 1),
            freq_start_hz=round(freq_start, 1),
            freq_end_hz=round(freq_end, 1),
            freq_mean_hz=round(freq_mean, 1),
            freq_trajectory=traj,
            freq_range_hz=round(freq_range, 1),
            fm_rate_hz=round(fm_rate, 1),
            fm_depth=round(fm_depth, 3),
            fm_character=fm_char,
            attack_ms=round(attack_ms, 1),
            release_ms=round(release_ms, 1),
            peak_amplitude=round(peak_amp, 3),
        ))

    codec = _codec_sketch(events)

    return SoundAnalysis(
        filename=path.name,
        emotion_label=label,
        duration_s=round(duration, 3),
        sample_rate=sr,
        rms_amplitude=round(rms, 4),
        event_count=len(events),
        events=events,
        suggested_codec=codec,
    )


def plot_spectrogram(path: str, out_dir: str) -> None:
    if not HAS_MPL:
        print("matplotlib not available, skipping plots")
        return
    y, sr = _load(path)
    stem = Path(path).stem
    fig, ax = plt.subplots(figsize=(12, 4))
    D = librosa.amplitude_to_db(np.abs(librosa.stft(y, hop_length=128)), ref=np.max)
    librosa.display.specshow(D, sr=sr, hop_length=128, x_axis="time", y_axis="hz",
                             ax=ax, cmap="magma", vmin=-60)
    # Overlay pitch track
    f0, voiced, _ = librosa.pyin(y, fmin=130, fmax=4200, sr=sr, hop_length=128)
    times = librosa.times_like(f0, sr=sr, hop_length=128)
    ax.plot(times, f0, color="cyan", linewidth=1.5, label="F0")
    ax.set_title(f"R2D2 — {stem}")
    ax.set_ylim(0, 4000)
    ax.legend()
    plt.tight_layout()
    out_path = os.path.join(out_dir, f"{stem}_spectrogram.png")
    plt.savefig(out_path, dpi=120)
    plt.close()
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_analysis(a: SoundAnalysis) -> None:
    print(f"\n{'='*60}")
    print(f"  {a.filename}  [{a.emotion_label}]")
    print(f"  Duration: {a.duration_s:.2f}s   SR: {a.sample_rate} Hz   "
          f"RMS: {a.rms_amplitude:.4f}   Events: {a.event_count}")
    print(f"{'='*60}")
    for ev in a.events:
        traj_arrow = {"up": "↑", "down": "↓", "stable": "→", "complex": "~"}.get(ev.freq_trajectory, "?")
        print(f"  [{ev.index}] {ev.start_s:.2f}s–{ev.end_s:.2f}s  "
              f"{ev.duration_ms:.0f}ms  "
              f"fc={ev.freq_mean_hz:.0f}Hz {traj_arrow}  "
              f"({ev.freq_start_hz:.0f}→{ev.freq_end_hz:.0f}Hz)  "
              f"FM:{ev.fm_character} rate={ev.fm_rate_hz:.1f}Hz depth={ev.fm_depth:.2f}  "
              f"atk={ev.attack_ms:.0f}ms rel={ev.release_ms:.0f}ms")
    print(f"\n  Suggested R2SC:")
    print(f"    {a.suggested_codec}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze R2D2 sound files")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--sounds_dir", help="Directory containing MP3 files")
    grp.add_argument("--file", help="Single MP3 file to analyze")
    parser.add_argument("--plot", action="store_true", help="Save spectrogram PNGs")
    parser.add_argument("--out_dir", default=None,
                        help="Output directory for JSON/PNG (default: analysis/ next to sounds)")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
        base_dir = os.path.dirname(args.file)
    else:
        sounds_dir = args.sounds_dir.rstrip("/")
        files = sorted([
            os.path.join(sounds_dir, f)
            for f in os.listdir(sounds_dir)
            if f.lower().endswith(".mp3")
        ])
        base_dir = sounds_dir

    out_dir = args.out_dir or os.path.join(os.path.dirname(base_dir), "analysis")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Analyzing {len(files)} file(s) → {out_dir}/")

    all_results = {}
    for fpath in files:
        print(f"\nProcessing: {os.path.basename(fpath)} ...", end=" ", flush=True)
        try:
            result = analyze_file(fpath)
            print("OK")
            print_analysis(result)

            # Save individual JSON
            out_json = os.path.join(out_dir, f"{Path(fpath).stem}.json")
            with open(out_json, "w") as f:
                json.dump(asdict(result), f, indent=2)

            if args.plot:
                plot_spectrogram(fpath, out_dir)

            all_results[result.emotion_label] = asdict(result)

        except Exception as exc:
            print(f"ERROR: {exc}")
            import traceback; traceback.print_exc()

    # Summary JSON
    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n\nSummary written to: {summary_path}")
    print("\nNext step: share the contents of analysis/summary.json")
    print("to finalize the R2D2 Sound Codec (R2SC) design.")


if __name__ == "__main__":
    main()
