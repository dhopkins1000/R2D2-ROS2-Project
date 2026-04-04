#!/usr/bin/env python3
"""
R2D2 Sound Synthesizer
Generates all phoneme and phrase .wav files using FM synthesis.

Usage:
    python3 synth.py              # Generate all sounds
    python3 synth.py --preview    # Print library summary only

Dependencies: numpy
    pip install numpy

Outputs to: src/r2d2_audio/sounds/  (created if missing)
"""

import argparse
import os
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SAMPLE_RATE = 44100
# Relative to this script: ../sounds/
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "sounds")


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------

@dataclass
class Phoneme:
    """
    FM-synthesized sound primitive with attack/release envelope.

    FM formula:  y(t) = A * sin( phase(t) + beta * sin(2pi * fm * t) )
    where phase(t) integrates the (possibly swept) carrier frequency.

    Parameters
    ----------
    name        : identifier, used as filename
    duration    : length in seconds
    fc          : carrier frequency in Hz (start frequency for sweeps)
    fc_end      : if set, carrier sweeps linearly from fc to fc_end
    fm          : modulator frequency in Hz (0 = no FM)
    beta        : FM modulation index (0 = pure sine; higher = richer/wobblier)
    amplitude   : peak amplitude 0..1
    attack      : fade-in time in seconds
    release     : fade-out time in seconds
    """
    name: str
    duration: float
    fc: float
    fc_end: Optional[float] = None
    fm: float = 0.0
    beta: float = 0.0
    amplitude: float = 0.85
    attack: float = 0.010
    release: float = 0.025


@dataclass
class Phrase:
    """
    Sequence of phoneme names played with a small silence gap between them.
    """
    name: str
    phonemes: list
    gap: float = 0.055   # silence between phonemes in seconds


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


def synthesize(phoneme: Phoneme, sr: int = SAMPLE_RATE) -> np.ndarray:
    n = int(phoneme.duration * sr)
    t = np.arange(n, dtype=np.float64) / sr

    # Carrier frequency: linear sweep or constant
    if phoneme.fc_end is not None:
        fc_t = np.linspace(phoneme.fc, phoneme.fc_end, n)
    else:
        fc_t = np.full(n, phoneme.fc)

    # Phase via cumulative sum (correct for both sweeps and FM)
    carrier_phase = 2.0 * np.pi * np.cumsum(fc_t) / sr
    fm_phase = phoneme.beta * np.sin(2.0 * np.pi * phoneme.fm * t) if phoneme.fm > 0 else 0.0

    signal = phoneme.amplitude * np.sin(carrier_phase + fm_phase)
    signal *= _envelope(n, phoneme.attack, phoneme.release, sr)
    return signal.astype(np.float32)


def build_phrase(phrase: Phrase, library: dict, sr: int = SAMPLE_RATE) -> np.ndarray:
    silence = np.zeros(int(phrase.gap * sr), dtype=np.float32)
    parts = []
    for name in phrase.phonemes:
        if name not in library:
            raise KeyError(f"Unknown phoneme '{name}' in phrase '{phrase.name}'")
        parts.append(synthesize(library[name], sr))
        parts.append(silence)
    return np.concatenate(parts[:-1])  # drop trailing silence


def save_wav(samples: np.ndarray, path: str, sr: int = SAMPLE_RATE) -> None:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_int16 = (pcm * 32767).astype(np.int16)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm_int16.tobytes())


# ---------------------------------------------------------------------------
# Sound library definitions
# ---------------------------------------------------------------------------
#
# FM parameter guide:
#   beta = 0         -> pure sine tone
#   beta 20-80       -> light wobble / vibrato
#   beta 100-250     -> rich R2D2 warble
#   fm 5-15 Hz       -> slow wobble (emotional colouring)
#   fm 30-60 Hz      -> fast trill (excitement / alarm)
#
# Carrier frequencies kept in 500-2000 Hz range for speaker clarity on Pi.

PHONEME_LIBRARY: dict = {
    # --- Simple chirps / beeps ---
    "chirp_hi_short": Phoneme(
        "chirp_hi_short", duration=0.10, fc=1600,
        attack=0.005, release=0.020
    ),
    "chirp_lo_short": Phoneme(
        "chirp_lo_short", duration=0.12, fc=680,
        attack=0.005, release=0.020
    ),
    "chirp_hi_long": Phoneme(
        "chirp_hi_long", duration=0.28, fc=1400,
        fm=18, beta=35,
        attack=0.010, release=0.030
    ),
    "blip_neutral": Phoneme(
        "blip_neutral", duration=0.08, fc=920,
        attack=0.003, release=0.012
    ),
    "alert_beep": Phoneme(
        "alert_beep", duration=0.14, fc=1950,
        attack=0.004, release=0.012
    ),

    # --- Frequency sweeps (define R2D2's sentence intonation) ---
    "sweep_up_fast": Phoneme(
        "sweep_up_fast", duration=0.20, fc=520, fc_end=1750,
        attack=0.010, release=0.020
    ),
    "sweep_up_slow": Phoneme(
        "sweep_up_slow", duration=0.40, fc=420, fc_end=1450,
        attack=0.020, release=0.035
    ),
    "sweep_down_fast": Phoneme(
        "sweep_down_fast", duration=0.20, fc=1750, fc_end=520,
        attack=0.010, release=0.020
    ),
    "sweep_down_slow": Phoneme(
        "sweep_down_slow", duration=0.40, fc=1450, fc_end=400,
        attack=0.020, release=0.055
    ),
    "sweep_up_rich": Phoneme(
        "sweep_up_rich", duration=0.30, fc=550, fc_end=1600,
        fm=12, beta=80,
        attack=0.015, release=0.030
    ),

    # --- Wobbles / warbles (R2D2's emotional core) ---
    "wobble_happy": Phoneme(
        "wobble_happy", duration=0.55, fc=900,
        fm=8, beta=210,
        attack=0.030, release=0.055
    ),
    "wobble_curious": Phoneme(
        "wobble_curious", duration=0.45, fc=800, fc_end=1100,
        fm=10, beta=160,
        attack=0.025, release=0.045
    ),
    "wobble_sad": Phoneme(
        "wobble_sad", duration=0.60, fc=720, fc_end=480,
        fm=5, beta=140,
        attack=0.030, release=0.090
    ),

    # --- Trills (fast modulation = excitement / urgency) ---
    "trill_excited": Phoneme(
        "trill_excited", duration=0.40, fc=1200,
        fm=48, beta=175,
        attack=0.020, release=0.045
    ),
    "trill_alarm": Phoneme(
        "trill_alarm", duration=0.35, fc=1500,
        fm=60, beta=200,
        attack=0.008, release=0.020
    ),

    # --- Low / buzzy (negative / scared) ---
    "buzz_negative": Phoneme(
        "buzz_negative", duration=0.28, fc=340,
        fm=75, beta=2.8,
        attack=0.005, release=0.035
    ),

    # --- Extended / ambient ---
    "hum_processing": Phoneme(
        "hum_processing", duration=0.80, fc=740,
        fm=11, beta=90,
        attack=0.060, release=0.110
    ),
}


PHRASE_LIBRARY: dict = {
    # Confirmations
    "phrase_yes": Phrase(
        "phrase_yes",
        ["chirp_hi_short", "sweep_up_fast"]
    ),
    "phrase_yes_enthusiastic": Phrase(
        "phrase_yes_enthusiastic",
        ["sweep_up_fast", "chirp_hi_short", "wobble_happy"]
    ),

    # Negations
    "phrase_no": Phrase(
        "phrase_no",
        ["buzz_negative", "sweep_down_fast"]
    ),
    "phrase_no_firm": Phrase(
        "phrase_no_firm",
        ["buzz_negative", "buzz_negative", "sweep_down_slow"]
    ),

    # Questions
    "phrase_question": Phrase(
        "phrase_question",
        ["blip_neutral", "chirp_hi_short", "sweep_up_fast"]
    ),
    "phrase_question_confused": Phrase(
        "phrase_question_confused",
        ["chirp_lo_short", "sweep_up_fast", "sweep_down_fast", "chirp_hi_short"]
    ),

    # Emotions
    "phrase_happy": Phrase(
        "phrase_happy",
        ["wobble_happy", "trill_excited", "chirp_hi_short"]
    ),
    "phrase_sad": Phrase(
        "phrase_sad",
        ["wobble_sad", "sweep_down_slow"]
    ),
    "phrase_excited": Phrase(
        "phrase_excited",
        ["trill_excited", "sweep_up_fast", "chirp_hi_short", "trill_excited"]
    ),
    "phrase_scared": Phrase(
        "phrase_scared",
        ["trill_alarm", "buzz_negative", "sweep_down_fast"]
    ),
    "phrase_curious": Phrase(
        "phrase_curious",
        ["wobble_curious", "sweep_up_rich"]
    ),
    "phrase_frustrated": Phrase(
        "phrase_frustrated",
        ["buzz_negative", "chirp_lo_short", "sweep_down_fast", "buzz_negative"]
    ),

    # Functional
    "phrase_greeting": Phrase(
        "phrase_greeting",
        ["sweep_up_fast", "wobble_happy", "chirp_hi_short"]
    ),
    "phrase_goodbye": Phrase(
        "phrase_goodbye",
        ["wobble_happy", "sweep_down_slow"]
    ),
    "phrase_thinking": Phrase(
        "phrase_thinking",
        ["hum_processing", "blip_neutral", "blip_neutral"],
        gap=0.080
    ),
    "phrase_task_done": Phrase(
        "phrase_task_done",
        ["sweep_up_fast", "chirp_hi_long", "wobble_happy"]
    ),
    "phrase_task_failed": Phrase(
        "phrase_task_failed",
        ["sweep_down_slow", "buzz_negative", "chirp_lo_short"]
    ),
    "phrase_warning": Phrase(
        "phrase_warning",
        ["alert_beep", "alert_beep", "buzz_negative"],
        gap=0.040
    ),
    "phrase_startup": Phrase(
        "phrase_startup",
        ["sweep_up_slow", "wobble_happy", "trill_excited", "chirp_hi_short"],
        gap=0.070
    ),
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def generate_all(sr: int = SAMPLE_RATE, verbose: bool = True) -> None:
    output_dir = os.path.realpath(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    if verbose:
        print(f"Output directory: {output_dir}\n")
        print("── Phonemes ─────────────────────────────────")

    for name, phoneme in PHONEME_LIBRARY.items():
        samples = synthesize(phoneme, sr)
        path = os.path.join(output_dir, f"{name}.wav")
        save_wav(samples, path, sr)
        if verbose:
            print(f"  ✓  {name}.wav  ({phoneme.duration:.2f}s)")

    if verbose:
        print(f"\n── Phrases ──────────────────────────────────")

    for name, phrase in PHRASE_LIBRARY.items():
        samples = build_phrase(phrase, PHONEME_LIBRARY, sr)
        path = os.path.join(output_dir, f"{name}.wav")
        save_wav(samples, path, sr)
        if verbose:
            duration = len(samples) / sr
            print(f"  ✓  {name}.wav  ({duration:.2f}s)  <- {phrase.phonemes}")

    if verbose:
        print(
            f"\nDone. "
            f"{len(PHONEME_LIBRARY)} phonemes + {len(PHRASE_LIBRARY)} phrases "
            f"-> {output_dir}/"
        )


def preview() -> None:
    print(f"Phonemes ({len(PHONEME_LIBRARY)}):")
    for name, p in PHONEME_LIBRARY.items():
        print(f"  {name:<22}  fc={p.fc:.0f}Hz  fm={p.fm:.0f}Hz  beta={p.beta:.0f}  {p.duration:.2f}s")

    print(f"\nPhrases ({len(PHRASE_LIBRARY)}):")
    for name, p in PHRASE_LIBRARY.items():
        print(f"  {name:<30}  {' -> '.join(p.phonemes)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="R2D2 Sound Synthesizer")
    parser.add_argument("--preview", action="store_true", help="Print library, don't generate")
    parser.add_argument("--sr", type=int, default=SAMPLE_RATE, help="Sample rate (default 44100)")
    args = parser.parse_args()

    if args.preview:
        preview()
    else:
        generate_all(sr=args.sr)
