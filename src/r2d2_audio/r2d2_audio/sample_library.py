#!/usr/bin/env python3
"""
sample_library.py — R2D2 Sample Library

Loads and manages two tiers of R2D2 audio samples:

Tier 1 — Emotional phrases (full utterances, ~0.7-4s)
    Source: r2d2_sounds/ directory (MP3s provided by operator)
    Used for: direct playback of emotionally labelled sounds
    Processing: optional pitch shift ±1.5 semitones for variation

Tier 2 — Phonemes (micro-samples, ~0.1-0.8s)
    Source: r2d2_sounds/phonemes/ directory (WAVs from McGill R2D2 Simulator)
    Used for: generative sequencing — chained together to form new utterances
    Processing: pitch shift to target frequency, optional time stretch

HCR phoneme categories mapped to McGill samples:
    bump      -> boop.wav           soft low boop
    tone      -> berp.wav, dwip.wav  single beep/dip
    whistle   -> cleanwhistle.wav   rising organic whistle
    systle    -> bweep.wav          synthetic sweep-up
    reeo      -> dwaep.wav, dwoop.wav, wow.wav  complex sweeping tones
    birdsong  -> beepybeep.wav      multi-tone chitter
    growl     -> shortgrowl.wav     low mechanical growl

Sample rate: 22050 Hz
    R2D2 sounds are all below 4kHz. 22050 Hz covers up to 11025 Hz,
    which is well above what the 4Ohm/3W speaker can reproduce.
    Compared to 44100 Hz: ~50% RAM, ~2x faster pitch shift processing.

Dependencies: librosa, numpy, soundfile
    pip install librosa soundfile
"""

import io
import os
import random
import wave
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    import librosa
except ImportError:
    raise SystemExit("Missing dependency. Run: pip install librosa soundfile")

# 22050 Hz: covers 0-11025 Hz — more than sufficient for R2D2 sounds (<4kHz)
SAMPLE_RATE = 22050

# ---------------------------------------------------------------------------
# Phoneme category definitions
# ---------------------------------------------------------------------------

PHONEME_CATEGORIES: Dict[str, List[str]] = {
    "bump":     ["boop"],
    "tone":     ["berp", "dwip"],
    "whistle":  ["cleanwhistle"],
    "systle":   ["bweep"],
    "reeo":     ["dwaep", "dwoop", "wow"],
    "birdsong": ["beepybeep"],
    "growl":    ["shortgrowl"],
}

EMOTION_LABELS = [
    "acknowledged", "acknowledged_2",
    "chat", "chat2",
    "concerned", "curious",
    "excited", "excited_2", "excited_3",
    "surprised", "worried",
]


# ---------------------------------------------------------------------------
# SampleLibrary
# ---------------------------------------------------------------------------

class SampleLibrary:
    """
    Loads all samples into memory at startup for low-latency playback.
    Provides pitch-shifted and time-stretched variants on demand.

    Memory footprint at 22050 Hz:
        ~11 phrases x avg 1.5s = ~16.5s audio = ~1.4 MB
        ~10 phonemes x avg 0.4s = ~4s audio   = ~0.35 MB
        Total: ~1.8 MB
    """

    def __init__(self, sounds_dir: str):
        self._sounds_dir = Path(sounds_dir)
        self._phonemes_dir = self._sounds_dir / "phonemes"
        self._phrases: Dict[str, np.ndarray] = {}
        self._phonemes: Dict[str, np.ndarray] = {}
        self._load_phrases()
        self._load_phonemes()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_phrases(self) -> None:
        if not self._sounds_dir.exists():
            print(f"[SampleLibrary] Sounds dir not found: {self._sounds_dir}")
            return

        for path in sorted(self._sounds_dir.iterdir()):
            if path.suffix.lower() not in (".wav", ".mp3", ".ogg"):
                continue
            try:
                y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
                peak = np.max(np.abs(y))
                if peak > 0:
                    y = y / peak * 0.85
                name = path.stem.replace(" ", "_").replace("-", "_")
                self._phrases[name] = y
            except Exception as exc:
                print(f"[SampleLibrary] Could not load phrase {path.name}: {exc}")

        print(
            f"[SampleLibrary] Loaded {len(self._phrases)} phrase(s) "
            f"at {SAMPLE_RATE} Hz — "
            f"~{self._total_mb(self._phrases):.1f} MB"
        )

    def _load_phonemes(self) -> None:
        if not self._phonemes_dir.exists():
            print(f"[SampleLibrary] Phonemes dir not found: {self._phonemes_dir}")
            print("  -> Run tools/setup_samples.sh to populate it.")
            return

        for path in sorted(self._phonemes_dir.glob("*.wav")):
            try:
                y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
                peak = np.max(np.abs(y))
                if peak > 0:
                    y = y / peak * 0.85
                self._phonemes[path.stem] = y
            except Exception as exc:
                print(f"[SampleLibrary] Could not load phoneme {path.name}: {exc}")

        print(
            f"[SampleLibrary] Loaded {len(self._phonemes)} phoneme(s) "
            f"at {SAMPLE_RATE} Hz — "
            f"~{self._total_mb(self._phonemes):.1f} MB"
        )

    @staticmethod
    def _total_mb(d: Dict[str, np.ndarray]) -> float:
        return sum(a.nbytes for a in d.values()) / 1024 / 1024

    # ------------------------------------------------------------------
    # Phrase playback
    # ------------------------------------------------------------------

    def get_phrase(
        self,
        name: str,
        pitch_semitones: float = 0.0,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        y = self._phrases.get(name)
        if y is None:
            return None
        return self._process(y, pitch_semitones, speed)

    def get_random_phrase_variant(
        self,
        name: str,
        pitch_range: float = 1.5,
        speed_range: float = 0.08,
    ) -> Optional[np.ndarray]:
        """Return a phrase with small random pitch/speed variation for naturalness."""
        pitch = random.uniform(-pitch_range, pitch_range)
        speed = random.uniform(1.0 - speed_range, 1.0 + speed_range)
        return self.get_phrase(name, pitch, speed)

    def available_phrases(self) -> List[str]:
        return list(self._phrases.keys())

    # ------------------------------------------------------------------
    # Phoneme playback
    # ------------------------------------------------------------------

    def get_phoneme(
        self,
        name: str,
        pitch_semitones: float = 0.0,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        y = self._phonemes.get(name)
        if y is None:
            return None
        return self._process(y, pitch_semitones, speed)

    def get_phoneme_from_category(
        self,
        category: str,
        pitch_semitones: float = 0.0,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        candidates = PHONEME_CATEGORIES.get(category, [])
        if not candidates:
            return None
        name = random.choice(candidates)
        return self.get_phoneme(name, pitch_semitones, speed)

    def available_phonemes(self) -> List[str]:
        return list(self._phonemes.keys())

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process(
        self,
        y: np.ndarray,
        pitch_semitones: float,
        speed: float,
    ) -> np.ndarray:
        if abs(pitch_semitones) > 0.05:
            y = librosa.effects.pitch_shift(
                y, sr=SAMPLE_RATE, n_steps=pitch_semitones
            )
        if abs(speed - 1.0) > 0.02:
            y = librosa.effects.time_stretch(y, rate=speed)
        return y

    # ------------------------------------------------------------------
    # Audio rendering
    # ------------------------------------------------------------------

    def render_to_wav_bytes(self, samples: np.ndarray) -> bytes:
        """Convert float32 array to WAV bytes for aplay/afplay."""
        pcm = np.clip(samples, -1.0, 1.0)
        pcm_int16 = (pcm * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_int16.tobytes())
        return buf.getvalue()

    def chain(
        self,
        segments: List[np.ndarray],
        gap_s: float = 0.06,
    ) -> np.ndarray:
        """Concatenate audio segments with a silence gap between them."""
        silence = np.zeros(int(gap_s * SAMPLE_RATE), dtype=np.float32)
        parts = []
        for seg in segments:
            parts.append(seg)
            parts.append(silence)
        return np.concatenate(parts[:-1]) if parts else np.zeros(0, dtype=np.float32)
