#!/usr/bin/env python3
"""
R2D2 Voice Intent Mapper
Maps structured LLM output -> phrase sequence -> .wav filenames to play.

The LLM never knows about individual sounds. It outputs a small JSON object
describing *intent* and *emotion*, and this module decides which sounds to play.
This keeps the mapping in code (version-controlled, easy to tune) and keeps
the LLM prompt small and stable.

LLM output schema:
    {"speak": true, "intent": "task_complete", "emotion": "happy", "intensity": "high"}

Mapper output example:
    ["phrase_task_done", "phrase_happy"]
"""

import json
import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# LLM intent schema
# ---------------------------------------------------------------------------

VALID_INTENTS = {
    "affirmative",   # Yes / understood / will do
    "negative",      # No / refused / can't do
    "question",      # R2D2 is asking something
    "greeting",      # Hello / startup
    "goodbye",       # Signing off
    "task_complete", # Just finished something successfully
    "task_failed",   # Something went wrong
    "thinking",      # Processing / computing
    "warning",       # Obstacle / danger / alert
    "comment",       # General emotional reaction (rely on emotion field)
}

VALID_EMOTIONS = {
    "happy", "sad", "excited", "scared",
    "confused", "curious", "angry", "neutral",
}

VALID_INTENSITIES = {"low", "medium", "high"}


@dataclass
class R2D2Intent:
    intent: str
    emotion: str
    intensity: str
    speak: bool = True

    def __post_init__(self):
        self.intent    = self.intent    if self.intent    in VALID_INTENTS    else "comment"
        self.emotion   = self.emotion   if self.emotion   in VALID_EMOTIONS   else "neutral"
        self.intensity = self.intensity if self.intensity in VALID_INTENSITIES else "medium"


# ---------------------------------------------------------------------------
# Mapping table
#
# Structure:
#   (intent, intensity) -> list of possible phrase sequences
#   (comment, emotion)  -> list of possible phrase sequences
#
# Multiple options per key allow variety: one is chosen at random each call.
# Each option is a list of phrase names (defined in scripts/synth.py).
# ---------------------------------------------------------------------------

MAPPING: dict = {
    # -- Affirmative --------------------------------------------------------
    ("affirmative", "low"):    [["phrase_yes"]],
    ("affirmative", "medium"): [["phrase_yes"], ["phrase_yes", "phrase_happy"]],
    ("affirmative", "high"):   [["phrase_yes_enthusiastic"], ["phrase_yes", "phrase_excited"]],

    # -- Negative -----------------------------------------------------------
    ("negative", "low"):    [["phrase_no"]],
    ("negative", "medium"): [["phrase_no"], ["phrase_no", "phrase_sad"]],
    ("negative", "high"):   [["phrase_no_firm"], ["phrase_no_firm", "phrase_frustrated"]],

    # -- Question -----------------------------------------------------------
    ("question", "low"):    [["phrase_question"]],
    ("question", "medium"): [["phrase_question"], ["phrase_thinking", "phrase_question"]],
    ("question", "high"):   [["phrase_question_confused"], ["phrase_thinking", "phrase_question_confused"]],

    # -- Greeting -----------------------------------------------------------
    ("greeting", "low"):    [["phrase_greeting"]],
    ("greeting", "medium"): [["phrase_greeting"]],
    ("greeting", "high"):   [["phrase_startup"], ["phrase_excited", "phrase_greeting"]],

    # -- Goodbye ------------------------------------------------------------
    ("goodbye", "low"):    [["phrase_goodbye"]],
    ("goodbye", "medium"): [["phrase_goodbye"]],
    ("goodbye", "high"):   [["phrase_happy", "phrase_goodbye"]],

    # -- Task complete ------------------------------------------------------
    ("task_complete", "low"):    [["phrase_task_done"]],
    ("task_complete", "medium"): [["phrase_task_done"]],
    ("task_complete", "high"):   [["phrase_task_done", "phrase_happy"], ["phrase_excited", "phrase_task_done"]],

    # -- Task failed --------------------------------------------------------
    ("task_failed", "low"):    [["phrase_task_failed"]],
    ("task_failed", "medium"): [["phrase_task_failed"], ["phrase_task_failed", "phrase_sad"]],
    ("task_failed", "high"):   [["phrase_task_failed", "phrase_frustrated"]],

    # -- Thinking -----------------------------------------------------------
    ("thinking", "low"):    [["phrase_thinking"]],
    ("thinking", "medium"): [["phrase_thinking"]],
    ("thinking", "high"):   [["phrase_thinking", "phrase_question_confused"]],

    # -- Warning ------------------------------------------------------------
    ("warning", "low"):    [["phrase_warning"]],
    ("warning", "medium"): [["phrase_warning"]],
    ("warning", "high"):   [["phrase_warning", "phrase_warning"]],

    # -- Comment: pure emotion reactions ------------------------------------
    ("comment", "happy"):   [["phrase_happy"],      ["phrase_happy",   "phrase_excited"]],
    ("comment", "excited"):  [["phrase_excited"],    ["phrase_excited", "phrase_yes"]],
    ("comment", "sad"):      [["phrase_sad"]],
    ("comment", "scared"):   [["phrase_scared"],     ["phrase_scared",  "phrase_warning"]],
    ("comment", "confused"):  [["phrase_question_confused"]],
    ("comment", "curious"):   [["phrase_curious"],   ["phrase_question"]],
    ("comment", "angry"):     [["phrase_frustrated"], ["phrase_no",     "phrase_frustrated"]],
    ("comment", "neutral"):   [["phrase_thinking"]],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(intent: R2D2Intent) -> list:
    """
    Returns a list of phrase names to play in sequence.
    Falls back gracefully for unknown intent/emotion combinations.
    """
    key = (intent.intent, intent.intensity)

    if key in MAPPING:
        options = MAPPING[key]
    else:
        # Fallback: treat as comment + use emotion
        key = ("comment", intent.emotion)
        options = MAPPING.get(key, [["phrase_thinking"]])

    return random.choice(options)


def resolve_from_json(llm_json: str) -> dict:
    """
    Parse LLM JSON string and return the play sequence + metadata.

    Returns:
        {
            "speak": bool,
            "phrases": ["phrase_task_done", "phrase_happy"],
            "emotion": "happy",
            "intent": "task_complete",
            "intensity": "medium"
        }
    """
    data = json.loads(llm_json)

    if not data.get("speak", True):
        return {
            "speak": False, "phrases": [],
            "emotion": data.get("emotion", "neutral"),
            "intent": data.get("intent", "comment"),
            "intensity": data.get("intensity", "medium"),
        }

    intent = R2D2Intent(
        intent=data.get("intent", "comment"),
        emotion=data.get("emotion", "neutral"),
        intensity=data.get("intensity", "medium"),
        speak=data.get("speak", True),
    )

    return {
        "speak": True,
        "phrases": resolve(intent),
        "emotion": intent.emotion,
        "intent": intent.intent,
        "intensity": intent.intensity,
    }


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    examples = [
        '{"speak": true, "intent": "task_complete", "emotion": "happy",   "intensity": "high"}',
        '{"speak": true, "intent": "warning",       "emotion": "scared",  "intensity": "high"}',
        '{"speak": true, "intent": "question",      "emotion": "curious", "intensity": "medium"}',
        '{"speak": true, "intent": "negative",      "emotion": "angry",   "intensity": "low"}',
        '{"speak": false, "intent": "comment",      "emotion": "neutral", "intensity": "low"}',
        '{"speak": true, "intent": "greeting",      "emotion": "excited", "intensity": "high"}',
    ]

    print("Intent mapper demo\n" + "-" * 50)
    for ex in examples:
        result = resolve_from_json(ex)
        print(f"IN:  {json.loads(ex)}")
        print(f"OUT: {result['phrases']}")
        print()
