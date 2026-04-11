#!/usr/bin/env python3
"""
sample_library.py — R2D2 Sample Library

Loads and manages two tiers of R2D2 audio samples.

Performance strategy: pre-bake pitch-shifted variants at startup
-----------------------------------------------------------------
librosa.effects.pitch_shift() takes 1-3s per sample on the Pi 4.
Running it on every playback request causes 8+ second delays.

Solution: during __init__, pre-compute N_VARIANTS pitch-shifted versions
of every phrase and phoneme and cache them in RAM. Playback then just
picks a random cached variant — zero processing time at play time.

Memory impact at 22050 Hz with N_VARIANTS=5:
    Phrases:  11 x 5 variants x avg 1.5s  = ~6 MB
    Phonemes: 10 x 5 variants x avg 0.4s  = ~1.8 MB
    Total: ~8 MB  (well within Pi 4 8GB budget)

Sample rate: 22050 Hz (covers 0-11025 Hz, sufficient for R2D2 <4kHz)
"""

import io
import random
import wave
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    import librosa
except ImportError:
    raise SystemExit("Missing dependency. Run: pip install librosa soundfile")

SAMPLE_RATE = 22050

# Number of pitch-shifted variants to pre-bake per sample.
# Higher = more variety, more RAM, longer startup time.
N_VARIANTS = 5

# Pitch range for pre-baked phrase variants (± semitones)
PHRASE_PITCH_RANGE = 1.5

# Pitch range for pre-baked phoneme variants (± semitones)
PHONEME_PITCH_RANGE = 2.5

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
    Loads all samples and pre-bakes pitch-shifted variants at startup.
    Playback is instant — no processing happens at play time.
    """

    def __init__(self, sounds_dir: str):
        self._sounds_dir = Path(sounds_dir)
        self._phonemes_dir = self._sounds_dir / "phonemes"

        # Raw originals: {name: array}
        self._phrases_raw: Dict[str, np.ndarray] = {}
        self._phonemes_raw: Dict[str, np.ndarray] = {}

        # Pre-baked variants: {name: [array, array, ...]}
        self._phrases: Dict[str, List[np.ndarray]] = {}
        self._phonemes: Dict[str, List[np.ndarray]] = {}

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
                y = self._normalize(y)
                name = path.stem.replace(" ", "_").replace("-", "_")
                self._phrases_raw[name] = y
            except Exception as exc:
                print(f"[SampleLibrary] Could not load phrase {path.name}: {exc}")

        # Pre-bake variants
        for name, y in self._phrases_raw.items():
            self._phrases[name] = self._bake_variants(
                y, N_VARIANTS, PHRASE_PITCH_RANGE
            )
            print(f"[SampleLibrary] Phrase baked: {name} ({N_VARIANTS} variants)")

        mb = self._total_mb_variants(self._phrases)
        print(f"[SampleLibrary] {len(self._phrases)} phrase(s) ready — ~{mb:.1f} MB")

    def _load_phonemes(self) -> None:
        if not self._phonemes_dir.exists():
            print(f"[SampleLibrary] Phonemes dir not found: {self._phonemes_dir}")
            print("  -> Run tools/setup_samples.sh to populate it.")
            return

        for path in sorted(self._phonemes_dir.glob("*.wav")):
            try:
                y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
                y = self._normalize(y)
                self._phonemes_raw[path.stem] = y
            except Exception as exc:
                print(f"[SampleLibrary] Could not load phoneme {path.name}: {exc}")

        # Pre-bake variants
        for name, y in self._phonemes_raw.items():
            self._phonemes[name] = self._bake_variants(
                y, N_VARIANTS, PHONEME_PITCH_RANGE
            )
            print(f"[SampleLibrary] Phoneme baked: {name} ({N_VARIANTS} variants)")

        mb = self._total_mb_variants(self._phonemes)
        print(f"[SampleLibrary] {len(self._phonemes)} phoneme(s) ready — ~{mb:.1f} MB")

    def _bake_variants(
        self,
        y: np.ndarray,
        n: int,
        pitch_range: float,
    ) -> List[np.ndarray]:
        """
        Pre-compute n pitch-shifted variants evenly spread across ±pitch_range.
        First variant is always the original (pitch=0) for clean reference.
        """
        variants = [y.copy()]  # variant 0: no shift
        pitches = np.linspace(-pitch_range, pitch_range, n - 1)
        for semitones in pitches:
            try:
                shifted = librosa.effects.pitch_shift(
                    y, sr=SAMPLE_RATE, n_steps=float(semitones)
                )
                variants.append(shifted)
            except Exception as exc:
                print(f"[SampleLibrary] Pitch shift failed ({semitones:.1f}st): {exc}")
                variants.append(y.copy())
        return variants

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(y: np.ndarray) -> np.ndarray:
        peak = np.max(np.abs(y))
        return (y / peak * 0.85) if peak > 0 else y

    @staticmethod
    def _total_mb_variants(d: Dict[str, List[np.ndarray]]) -> float:
        return sum(
            a.nbytes for variants in d.values() for a in variants
        ) / 1024 / 1024

    # ------------------------------------------------------------------
    # Phrase playback  (instant — just picks a cached variant)
    # ------------------------------------------------------------------

    def get_random_phrase_variant(
        self,
        name: str,
        pitch_range: float = 1.5,   # kept for API compat, ignored (pre-baked)
        speed_range: float = 0.08,  # kept for API compat, ignored
    ) -> Optional[np.ndarray]:
        variants = self._phrases.get(name)
        if not variants:
            return None
        return random.choice(variants).copy()

    def get_phrase(
        self,
        name: str,
        pitch_semitones: float = 0.0,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        # For API compatibility — just pick a random variant
        return self.get_random_phrase_variant(name)

    def available_phrases(self) -> List[str]:
        return list(self._phrases.keys())

    # ------------------------------------------------------------------
    # Phoneme playback  (instant — just picks a cached variant)
    # ------------------------------------------------------------------

    def get_phoneme(
        self,
        name: str,
        pitch_semitones: float = 0.0,
        speed: float = 1.0,
    ) -> Optional[np.ndarray]:
        variants = self._phonemes.get(name)
        if not variants:
            return None
        return random.choice(variants).copy()

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
        return self.get_phoneme(name)

    def available_phonemes(self) -> List[str]:
        return list(self._phonemes.keys())

    # ------------------------------------------------------------------
    # Audio rendering
    # ------------------------------------------------------------------

    def render_to_wav_bytes(self, samples: np.ndarray) -> bytes:
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
        silence = np.zeros(int(gap_s * SAMPLE_RATE), dtype=np.float32)
        parts = []
        for seg in segments:
            parts.append(seg)
            parts.append(silence)
        return np.concatenate(parts[:-1]) if parts else np.zeros(0, dtype=np.float32)
