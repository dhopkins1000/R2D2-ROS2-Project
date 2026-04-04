# ADR 006: R2D2 Voice Language Design

**Date:** 2026-04-04  
**Status:** Accepted

## Context

R2D2 should communicate vocally using characteristic beep sequences, not
human speech. This requires a system that can:

1. Generate a library of R2D2-style sounds
2. Allow the LLM to trigger vocal reactions without micro-managing individual sounds
3. Play sounds on demand via the ROS2 system

Key constraints:
- Must work offline and with low latency on the Raspberry Pi 4
- LLM prompt size must remain small and stable
- Sound library must be easy to tune without touching LLM prompts
- No dependency on external audio synthesis services

## Decision

### Layered architecture

Three distinct layers are kept strictly separated:

```
LLM (intent + emotion + intensity)
        |
        v
intent_mapper.py  (code-level mapping, not in prompt)
        |
        v
phrase sequence  ["phrase_task_done", "phrase_happy"]
        |
        v
voice_node.py  ->  aplay  ->  speaker
```

The LLM **never** knows about individual sound files or phoneme names.
It only outputs three fields: `intent`, `emotion`, and `intensity`.

### Sound generation: FM synthesis

All sounds are generated programmatically via FM (Frequency Modulation)
synthesis using numpy. This ensures:
- Reproducible, consistent sounds
- No copyright concerns
- Easy parameter tuning (carrier frequency, modulation index, sweep)
- No microphone recording or manual editing required

The synthesis script (`scripts/synth.py`) generates two levels:
- **Phonemes**: 14 atomic sounds (chirps, sweeps, wobbles, trills, buzzes)
- **Phrases**: 18 pre-composed sequences with semantic meaning

Generated `.wav` files are stored at `src/r2d2_audio/sounds/` (git-ignored
as binary files; regenerated on the Pi with `python3 scripts/synth.py`).

### Intent vocabulary

The LLM interface is deliberately minimal:

| Field       | Values |
|-------------|--------|
| `intent`    | affirmative, negative, question, greeting, goodbye, task_complete, task_failed, thinking, warning, comment |
| `emotion`   | happy, sad, excited, scared, confused, curious, angry, neutral |
| `intensity` | low, medium, high |

### Sound file management

`.wav` files are **not committed to git** (binary files, generated artefacts).
They are regenerated on the Pi by running `python3 src/r2d2_audio/scripts/synth.py`.
This is documented in the package README and should be part of the Pi setup script.

## Alternatives considered

### LLM selects sound IDs directly
Rejected. Would require exposing the full sound library in every LLM prompt,
increase prompt token count, and cause hallucinated or invalid IDs.

### Pre-recorded samples (e.g. from the films)
Rejected for initial implementation due to copyright concerns and difficulty
of achieving consistent quality. Can be added later as phrase overrides.

### Text-to-speech with voice synthesis (e.g. Coqui, Piper)
Rejected. TTS produces human speech, not R2D2 beeps.

### Single-file sound library (one long .wav per phrase)
Rejected in favour of the phoneme/phrase split which allows flexible
composition and easier iteration on individual sound atoms.

## Consequences

- Sound library must be regenerated after `synth.py` changes (on every Pi clone/setup)
- Adding new sounds requires editing `synth.py` only; LLM prompt is unaffected
- New intent/emotion combinations require editing `intent_mapper.py` only
- `aplay` must be available on the Pi (part of standard ALSA utils)
- The `numpy` package must be installed on the Pi (`pip install numpy`)
