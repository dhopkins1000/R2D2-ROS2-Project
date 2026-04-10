#!/usr/bin/env python3
"""
utterance_builder.py — R2D2 Utterance Builder

Maps LLM intent/emotion JSON to a concrete audio sequence using
the SampleLibrary. Two strategies:

Strategy A — Phrase (Tier 1):
    Play one of the labelled emotional phrase samples directly.
    Best for: strong, contextually clear emotional moments.
    Variation: small random pitch/speed shift each time.

Strategy B — Generative (Tier 2):
    Chain 2-4 phonemes from semantic categories.
    Best for: varied, ambient, or functional utterances.
    Variation: random phoneme selection + pitch shift per segment.

Each intent/emotion combination maps to a UtterancePlan that specifies
which strategy to use, with fallback options.
"""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from r2d2_audio.sample_library import SampleLibrary, PHONEME_CATEGORIES


# ---------------------------------------------------------------------------
# Utterance plan data types
# ---------------------------------------------------------------------------

@dataclass
class PhrasePlan:
    """Play a named emotional phrase sample."""
    candidates: List[str]          # try these in order until one is available
    pitch_range: float = 1.5       # ± semitones for variation
    speed_range: float = 0.07      # ± fraction for variation


@dataclass
class GenerativePlan:
    """
    Chain phoneme categories.
    Each step is (category, pitch_semitones_offset, speed).
    pitch_base shifts all phonemes up/down (for high/low emotional register).
    """
    steps: List[str]               # list of category names
    pitch_base: float = 0.0        # overall pitch offset in semitones
    pitch_spread: float = 2.0      # random per-step variation ± semitones
    gap_s: float = 0.06


@dataclass
class UtterancePlan:
    primary: object                # PhrasePlan or GenerativePlan
    secondary: Optional[object] = None   # fallback if primary has no samples


# ---------------------------------------------------------------------------
# Utterance plan table
# ---------------------------------------------------------------------------
# Keys: (intent, intensity) or ("comment", emotion)
# HCR insight: R2 is ~75% afraid — fear/excitement combos are most common.

PLAN_TABLE = {
    # -- Affirmative -------------------------------------------------------
    ("affirmative", "low"):    UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("affirmative", "medium"): UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("affirmative", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"]),
        GenerativePlan(["birdsong", "tone", "whistle"], pitch_base=2.0)
    ),

    # -- Negative ----------------------------------------------------------
    ("negative", "low"):    UtterancePlan(
        GenerativePlan(["growl", "tone"], pitch_base=-3.0)
    ),
    ("negative", "medium"): UtterancePlan(
        GenerativePlan(["growl", "bump", "growl"], pitch_base=-3.0)
    ),
    ("negative", "high"):   UtterancePlan(
        GenerativePlan(["growl", "growl", "bump"], pitch_base=-5.0)
    ),

    # -- Question ----------------------------------------------------------
    ("question", "low"):    UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["tone", "systle"], pitch_base=1.0)
    ),
    ("question", "medium"): UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["bump", "tone", "systle"], pitch_base=1.0)
    ),
    ("question", "high"):   UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["tone", "reeo", "systle"], pitch_base=2.0)
    ),

    # -- Greeting ----------------------------------------------------------
    ("greeting", "low"):    UtterancePlan(
        GenerativePlan(["whistle", "bump"], pitch_base=1.0)
    ),
    ("greeting", "medium"): UtterancePlan(
        PhrasePlan(["excited"]),
        GenerativePlan(["whistle", "birdsong", "tone"], pitch_base=1.0)
    ),
    ("greeting", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2"]),
        GenerativePlan(["birdsong", "whistle", "reeo", "tone"], pitch_base=2.0)
    ),

    # -- Goodbye -----------------------------------------------------------
    ("goodbye", "low"):    UtterancePlan(
        GenerativePlan(["reeo", "bump"], pitch_base=-1.0)
    ),
    ("goodbye", "medium"): UtterancePlan(
        GenerativePlan(["whistle", "reeo"], pitch_base=0.0)
    ),
    ("goodbye", "high"):   UtterancePlan(
        PhrasePlan(["excited"]),
        GenerativePlan(["birdsong", "reeo", "bump"], pitch_base=0.0)
    ),

    # -- Task complete -----------------------------------------------------
    ("task_complete", "low"):    UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("task_complete", "medium"): UtterancePlan(
        PhrasePlan(["acknowledged", "excited"]),
        GenerativePlan(["tone", "whistle", "bump"], pitch_base=2.0)
    ),
    ("task_complete", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"]),
        GenerativePlan(["birdsong", "whistle", "reeo"], pitch_base=3.0)
    ),

    # -- Task failed -------------------------------------------------------
    ("task_failed", "low"):    UtterancePlan(
        PhrasePlan(["worried"]),
        GenerativePlan(["growl", "bump"], pitch_base=-2.0)
    ),
    ("task_failed", "medium"): UtterancePlan(
        PhrasePlan(["worried", "concerned"]),
        GenerativePlan(["growl", "reeo", "bump"], pitch_base=-3.0)
    ),
    ("task_failed", "high"):   UtterancePlan(
        PhrasePlan(["concerned", "worried"]),
        GenerativePlan(["growl", "growl", "reeo"], pitch_base=-4.0)
    ),

    # -- Thinking ----------------------------------------------------------
    ("thinking", "low"):    UtterancePlan(
        GenerativePlan(["bump", "tone"], pitch_base=0.0, gap_s=0.12)
    ),
    ("thinking", "medium"): UtterancePlan(
        GenerativePlan(["reeo", "bump", "tone"], pitch_base=0.0, gap_s=0.10)
    ),
    ("thinking", "high"):   UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["reeo", "bump", "tone", "bump"], pitch_base=0.0, gap_s=0.10)
    ),

    # -- Warning -----------------------------------------------------------
    ("warning", "low"):    UtterancePlan(
        PhrasePlan(["concerned"]),
        GenerativePlan(["tone", "growl"], pitch_base=-2.0)
    ),
    ("warning", "medium"): UtterancePlan(
        PhrasePlan(["concerned", "worried"]),
        GenerativePlan(["tone", "tone", "growl"], pitch_base=-2.0, gap_s=0.04)
    ),
    ("warning", "high"):   UtterancePlan(
        PhrasePlan(["worried"]),
        GenerativePlan(["tone", "tone", "tone", "growl"], pitch_base=-3.0, gap_s=0.04)
    ),

    # -- Comment: pure emotions --------------------------------------------
    ("comment", "happy"):   UtterancePlan(
        PhrasePlan(["excited", "acknowledged"]),
        GenerativePlan(["birdsong", "whistle"], pitch_base=2.0)
    ),
    ("comment", "excited"):  UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"]),
        GenerativePlan(["birdsong", "reeo", "whistle"], pitch_base=3.0)
    ),
    ("comment", "sad"):      UtterancePlan(
        PhrasePlan(["worried"]),
        GenerativePlan(["growl", "reeo"], pitch_base=-4.0)
    ),
    ("comment", "scared"):   UtterancePlan(
        PhrasePlan(["worried", "concerned"]),
        GenerativePlan(["tone", "growl", "reeo"], pitch_base=-3.0)
    ),
    ("comment", "confused"): UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["reeo", "tone", "systle"], pitch_base=0.0)
    ),
    ("comment", "curious"):  UtterancePlan(
        PhrasePlan(["curious"]),
        GenerativePlan(["bump", "systle", "reeo"], pitch_base=1.0)
    ),
    ("comment", "angry"):    UtterancePlan(
        GenerativePlan(["growl", "bump", "growl"], pitch_base=-4.0)
    ),
    ("comment", "neutral"):  UtterancePlan(
        GenerativePlan(["bump", "tone"], pitch_base=0.0, gap_s=0.10)
    ),
}

# Startup sound — special case
STARTUP_PLAN = UtterancePlan(
    PhrasePlan(["excited", "excited_2"], pitch_range=1.0),
    GenerativePlan(["birdsong", "reeo", "whistle", "bump"], pitch_base=1.0)
)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class UtteranceBuilder:

    def __init__(self, library: SampleLibrary):
        self._lib = library

    def build(
        self,
        intent: str,
        emotion: str,
        intensity: str,
    ) -> Optional[np.ndarray]:
        """
        Build audio for the given intent/emotion/intensity.
        Returns float32 numpy array or None on failure.
        """
        # Look up plan
        key = (intent, intensity)
        plan = PLAN_TABLE.get(key)
        if plan is None:
            key = ("comment", emotion)
            plan = PLAN_TABLE.get(key)
        if plan is None:
            plan = PLAN_TABLE[("comment", "neutral")]

        # Try primary, then secondary
        audio = self._execute(plan.primary)
        if audio is None and plan.secondary is not None:
            audio = self._execute(plan.secondary)
        return audio

    def build_startup(self) -> Optional[np.ndarray]:
        audio = self._execute(STARTUP_PLAN.primary)
        if audio is None:
            audio = self._execute(STARTUP_PLAN.secondary)
        return audio

    # ------------------------------------------------------------------

    def _execute(self, plan) -> Optional[np.ndarray]:
        if isinstance(plan, PhrasePlan):
            return self._execute_phrase(plan)
        elif isinstance(plan, GenerativePlan):
            return self._execute_generative(plan)
        return None

    def _execute_phrase(self, plan: PhrasePlan) -> Optional[np.ndarray]:
        for name in plan.candidates:
            audio = self._lib.get_random_phrase_variant(
                name,
                pitch_range=plan.pitch_range,
                speed_range=plan.speed_range,
            )
            if audio is not None:
                return audio
        return None

    def _execute_generative(self, plan: GenerativePlan) -> Optional[np.ndarray]:
        segments = []
        for category in plan.steps:
            pitch = plan.pitch_base + random.uniform(
                -plan.pitch_spread, plan.pitch_spread
            )
            seg = self._lib.get_phoneme_from_category(category, pitch_semitones=pitch)
            if seg is not None:
                segments.append(seg)

        if not segments:
            return None
        return self._lib.chain(segments, gap_s=plan.gap_s)
