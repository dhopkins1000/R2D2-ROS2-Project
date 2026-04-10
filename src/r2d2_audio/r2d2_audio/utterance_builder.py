#!/usr/bin/env python3
"""
utterance_builder.py — R2D2 Utterance Builder

Maps LLM intent/emotion/intensity/verbosity JSON to a concrete audio
sequence using the SampleLibrary.

Verbosity (1-10)
---------------
Represents how much R2D2 has to say, proportional to the length of the
LLM's actual response. The LLM sets this based on its answer length:

    1-2   Very short  (single word answer, simple ack)
    3-4   Short       (one sentence)
    5-6   Medium      (a few sentences)
    7-8   Long        (paragraph)
    9-10  Very long   (detailed explanation, story)

Effect on audio output:
    Tier 1 (phrase):    low verbosity  -> phrase only
                        high verbosity -> phrase + extra phoneme tail
    Tier 2 (generative): scales number of phonemes in the chain
                          1 -> 1 phoneme, 10 -> up to 6 phonemes
"""

import random
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from r2d2_audio.sample_library import SampleLibrary, PHONEME_CATEGORIES


# ---------------------------------------------------------------------------
# Verbosity mapping
# ---------------------------------------------------------------------------

def _phoneme_count(verbosity: int) -> int:
    """
    Map verbosity 1-10 to number of phonemes for generative sequences.

        1-2  -> 1
        3-4  -> 2
        5-6  -> 3
        7-8  -> 4
        9-10 -> 5-6
    """
    v = max(1, min(10, verbosity))
    if v <= 2:  return 1
    if v <= 4:  return 2
    if v <= 6:  return 3
    if v <= 8:  return 4
    return random.randint(5, 6)


def _phrase_tail_count(verbosity: int) -> int:
    """
    Number of extra phonemes to append after a Tier 1 phrase.
    Only kicks in at verbosity >= 5.

        1-4  -> 0  (phrase alone is enough)
        5-6  -> 1
        7-8  -> 2
        9-10 -> 3
    """
    v = max(1, min(10, verbosity))
    if v <= 4:  return 0
    if v <= 6:  return 1
    if v <= 8:  return 2
    return 3


# ---------------------------------------------------------------------------
# Utterance plan data types
# ---------------------------------------------------------------------------

@dataclass
class PhrasePlan:
    """Play a named emotional phrase sample."""
    candidates: List[str]
    pitch_range: float = 1.5
    speed_range: float = 0.07
    # Categories for the optional phoneme tail (high verbosity)
    tail_categories: List[str] = None

    def __post_init__(self):
        if self.tail_categories is None:
            self.tail_categories = ["tone", "bump", "reeo", "whistle",
                                    "birdsong", "systle"]


@dataclass
class GenerativePlan:
    """
    Chain phoneme categories. The base_steps list defines the
    emotional character. Verbosity controls how many steps are
    actually used (up to len(base_steps) * repeats if needed).
    """
    base_steps: List[str]          # emotional character pattern
    pitch_base: float = 0.0
    pitch_spread: float = 2.0
    gap_s: float = 0.06


@dataclass
class UtterancePlan:
    primary: object
    secondary: Optional[object] = None


# ---------------------------------------------------------------------------
# Utterance plan table
# ---------------------------------------------------------------------------

PLAN_TABLE = {
    # -- Affirmative -------------------------------------------------------
    ("affirmative", "low"):    UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("affirmative", "medium"): UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("affirmative", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"],
                   tail_categories=["birdsong", "whistle", "tone"]),
        GenerativePlan(["birdsong", "tone", "whistle", "bump", "reeo", "tone"],
                       pitch_base=2.0)
    ),

    # -- Negative ----------------------------------------------------------
    ("negative", "low"):    UtterancePlan(
        GenerativePlan(["growl", "tone", "bump", "growl", "reeo", "bump"],
                       pitch_base=-3.0)
    ),
    ("negative", "medium"): UtterancePlan(
        GenerativePlan(["growl", "bump", "growl", "tone", "bump", "growl"],
                       pitch_base=-3.0)
    ),
    ("negative", "high"):   UtterancePlan(
        GenerativePlan(["growl", "growl", "bump", "growl", "tone", "growl"],
                       pitch_base=-5.0)
    ),

    # -- Question ----------------------------------------------------------
    ("question", "low"):    UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["tone", "systle", "bump", "reeo"]),
        GenerativePlan(["tone", "systle", "bump", "reeo", "tone", "systle"],
                       pitch_base=1.0)
    ),
    ("question", "medium"): UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["bump", "tone", "systle", "reeo"]),
        GenerativePlan(["bump", "tone", "systle", "reeo", "bump", "tone"],
                       pitch_base=1.0)
    ),
    ("question", "high"):   UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["tone", "reeo", "systle", "bump"]),
        GenerativePlan(["tone", "reeo", "systle", "bump", "reeo", "tone"],
                       pitch_base=2.0)
    ),

    # -- Greeting ----------------------------------------------------------
    ("greeting", "low"):    UtterancePlan(
        GenerativePlan(["whistle", "bump", "tone", "birdsong", "whistle", "bump"],
                       pitch_base=1.0)
    ),
    ("greeting", "medium"): UtterancePlan(
        PhrasePlan(["excited"],
                   tail_categories=["whistle", "birdsong", "tone", "reeo"]),
        GenerativePlan(["whistle", "birdsong", "tone", "reeo", "whistle", "bump"],
                       pitch_base=1.0)
    ),
    ("greeting", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2"],
                   tail_categories=["birdsong", "whistle", "reeo", "tone"]),
        GenerativePlan(["birdsong", "whistle", "reeo", "tone", "birdsong", "whistle"],
                       pitch_base=2.0)
    ),

    # -- Goodbye -----------------------------------------------------------
    ("goodbye", "low"):    UtterancePlan(
        GenerativePlan(["reeo", "bump", "whistle", "reeo", "bump", "tone"],
                       pitch_base=-1.0)
    ),
    ("goodbye", "medium"): UtterancePlan(
        GenerativePlan(["whistle", "reeo", "bump", "tone", "reeo", "whistle"],
                       pitch_base=0.0)
    ),
    ("goodbye", "high"):   UtterancePlan(
        PhrasePlan(["excited"],
                   tail_categories=["birdsong", "reeo", "bump", "whistle"]),
        GenerativePlan(["birdsong", "reeo", "bump", "whistle", "reeo", "tone"],
                       pitch_base=0.0)
    ),

    # -- Task complete -----------------------------------------------------
    ("task_complete", "low"):    UtterancePlan(
        PhrasePlan(["acknowledged", "acknowledged_2"])
    ),
    ("task_complete", "medium"): UtterancePlan(
        PhrasePlan(["acknowledged", "excited"],
                   tail_categories=["tone", "whistle", "bump", "reeo"]),
        GenerativePlan(["tone", "whistle", "bump", "reeo", "tone", "whistle"],
                       pitch_base=2.0)
    ),
    ("task_complete", "high"):   UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"],
                   tail_categories=["birdsong", "whistle", "reeo", "tone"]),
        GenerativePlan(["birdsong", "whistle", "reeo", "tone", "birdsong", "reeo"],
                       pitch_base=3.0)
    ),

    # -- Task failed -------------------------------------------------------
    ("task_failed", "low"):    UtterancePlan(
        PhrasePlan(["worried"],
                   tail_categories=["growl", "bump", "reeo", "tone"]),
        GenerativePlan(["growl", "bump", "reeo", "growl", "tone", "bump"],
                       pitch_base=-2.0)
    ),
    ("task_failed", "medium"): UtterancePlan(
        PhrasePlan(["worried", "concerned"],
                   tail_categories=["growl", "reeo", "bump", "tone"]),
        GenerativePlan(["growl", "reeo", "bump", "tone", "growl", "reeo"],
                       pitch_base=-3.0)
    ),
    ("task_failed", "high"):   UtterancePlan(
        PhrasePlan(["concerned", "worried"],
                   tail_categories=["growl", "growl", "reeo", "bump"]),
        GenerativePlan(["growl", "growl", "reeo", "bump", "growl", "tone"],
                       pitch_base=-4.0)
    ),

    # -- Thinking ----------------------------------------------------------
    ("thinking", "low"):    UtterancePlan(
        GenerativePlan(["bump", "tone", "bump", "reeo", "tone", "bump"],
                       pitch_base=0.0, gap_s=0.12)
    ),
    ("thinking", "medium"): UtterancePlan(
        GenerativePlan(["reeo", "bump", "tone", "bump", "reeo", "tone"],
                       pitch_base=0.0, gap_s=0.10)
    ),
    ("thinking", "high"):   UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["reeo", "bump", "tone", "bump"]),
        GenerativePlan(["reeo", "bump", "tone", "bump", "reeo", "bump"],
                       pitch_base=0.0, gap_s=0.10)
    ),

    # -- Warning -----------------------------------------------------------
    ("warning", "low"):    UtterancePlan(
        PhrasePlan(["concerned"],
                   tail_categories=["tone", "growl", "bump", "tone"]),
        GenerativePlan(["tone", "growl", "bump", "tone", "growl", "bump"],
                       pitch_base=-2.0)
    ),
    ("warning", "medium"): UtterancePlan(
        PhrasePlan(["concerned", "worried"],
                   tail_categories=["tone", "tone", "growl", "bump"]),
        GenerativePlan(["tone", "tone", "growl", "bump", "tone", "growl"],
                       pitch_base=-2.0, gap_s=0.04)
    ),
    ("warning", "high"):   UtterancePlan(
        PhrasePlan(["worried"],
                   tail_categories=["tone", "tone", "growl", "bump"]),
        GenerativePlan(["tone", "tone", "growl", "bump", "tone", "growl"],
                       pitch_base=-3.0, gap_s=0.04)
    ),

    # -- Comment: pure emotions --------------------------------------------
    ("comment", "happy"):   UtterancePlan(
        PhrasePlan(["excited", "acknowledged"],
                   tail_categories=["birdsong", "whistle", "tone", "reeo"]),
        GenerativePlan(["birdsong", "whistle", "tone", "reeo", "birdsong", "tone"],
                       pitch_base=2.0)
    ),
    ("comment", "excited"):  UtterancePlan(
        PhrasePlan(["excited", "excited_2", "excited_3"],
                   tail_categories=["birdsong", "reeo", "whistle", "tone"]),
        GenerativePlan(["birdsong", "reeo", "whistle", "tone", "birdsong", "reeo"],
                       pitch_base=3.0)
    ),
    ("comment", "sad"):      UtterancePlan(
        PhrasePlan(["worried"],
                   tail_categories=["growl", "reeo", "bump", "tone"]),
        GenerativePlan(["growl", "reeo", "bump", "tone", "growl", "reeo"],
                       pitch_base=-4.0)
    ),
    ("comment", "scared"):   UtterancePlan(
        PhrasePlan(["worried", "concerned"],
                   tail_categories=["tone", "growl", "reeo", "bump"]),
        GenerativePlan(["tone", "growl", "reeo", "bump", "tone", "growl"],
                       pitch_base=-3.0)
    ),
    ("comment", "confused"): UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["reeo", "tone", "systle", "bump"]),
        GenerativePlan(["reeo", "tone", "systle", "bump", "reeo", "systle"],
                       pitch_base=0.0)
    ),
    ("comment", "curious"):  UtterancePlan(
        PhrasePlan(["curious"],
                   tail_categories=["bump", "systle", "reeo", "tone"]),
        GenerativePlan(["bump", "systle", "reeo", "tone", "bump", "reeo"],
                       pitch_base=1.0)
    ),
    ("comment", "angry"):    UtterancePlan(
        GenerativePlan(["growl", "bump", "growl", "tone", "growl", "bump"],
                       pitch_base=-4.0)
    ),
    ("comment", "neutral"):  UtterancePlan(
        GenerativePlan(["bump", "tone", "bump", "reeo", "tone", "bump"],
                       pitch_base=0.0, gap_s=0.10)
    ),
}

STARTUP_PLAN = UtterancePlan(
    PhrasePlan(["excited", "excited_2"], pitch_range=1.0,
               tail_categories=["birdsong", "reeo", "whistle", "bump"]),
    GenerativePlan(["birdsong", "reeo", "whistle", "bump", "birdsong", "tone"],
                   pitch_base=1.0)
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
        verbosity: int = 5,
    ) -> Optional[np.ndarray]:
        """
        Build audio for the given parameters.

        Args:
            intent:    What R2D2 is communicating
            emotion:   R2D2's emotional state
            intensity: low / medium / high
            verbosity: 1-10, proportional to LLM response length

        Returns:
            float32 numpy array or None on failure.
        """
        verbosity = max(1, min(10, verbosity))

        key = (intent, intensity)
        plan = PLAN_TABLE.get(key)
        if plan is None:
            key = ("comment", emotion)
            plan = PLAN_TABLE.get(key)
        if plan is None:
            plan = PLAN_TABLE[("comment", "neutral")]

        audio = self._execute(plan.primary, verbosity)
        if audio is None and plan.secondary is not None:
            audio = self._execute(plan.secondary, verbosity)
        return audio

    def build_startup(self) -> Optional[np.ndarray]:
        # Startup always plays at verbosity 7 — moderately expressive
        audio = self._execute(STARTUP_PLAN.primary, verbosity=7)
        if audio is None:
            audio = self._execute(STARTUP_PLAN.secondary, verbosity=7)
        return audio

    # ------------------------------------------------------------------

    def _execute(self, plan, verbosity: int) -> Optional[np.ndarray]:
        if isinstance(plan, PhrasePlan):
            return self._execute_phrase(plan, verbosity)
        elif isinstance(plan, GenerativePlan):
            return self._execute_generative(plan, verbosity)
        return None

    def _execute_phrase(self, plan: PhrasePlan, verbosity: int) -> Optional[np.ndarray]:
        # Try to find a phrase
        phrase_audio = None
        for name in plan.candidates:
            phrase_audio = self._lib.get_random_phrase_variant(
                name,
                pitch_range=plan.pitch_range,
                speed_range=plan.speed_range,
            )
            if phrase_audio is not None:
                break

        if phrase_audio is None:
            return None

        # High verbosity: append a phoneme tail
        tail_count = _phrase_tail_count(verbosity)
        if tail_count == 0 or not plan.tail_categories:
            return phrase_audio

        tail_segments = []
        # Cycle through tail_categories to fill tail_count slots
        for i in range(tail_count):
            cat = plan.tail_categories[i % len(plan.tail_categories)]
            pitch = random.uniform(-1.5, 1.5)
            seg = self._lib.get_phoneme_from_category(cat, pitch_semitones=pitch)
            if seg is not None:
                tail_segments.append(seg)

        if not tail_segments:
            return phrase_audio

        tail_audio = self._lib.chain(tail_segments, gap_s=0.07)
        return self._lib.chain([phrase_audio, tail_audio], gap_s=0.10)

    def _execute_generative(self, plan: GenerativePlan, verbosity: int) -> Optional[np.ndarray]:
        n = _phoneme_count(verbosity)
        # Cycle through base_steps to fill n slots
        steps = [
            plan.base_steps[i % len(plan.base_steps)]
            for i in range(n)
        ]
        segments = []
        for category in steps:
            pitch = plan.pitch_base + random.uniform(
                -plan.pitch_spread, plan.pitch_spread
            )
            seg = self._lib.get_phoneme_from_category(category, pitch_semitones=pitch)
            if seg is not None:
                segments.append(seg)

        if not segments:
            return None
        return self._lib.chain(segments, gap_s=plan.gap_s)
