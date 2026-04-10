# ADR 007: R2D2 Sound Codec (R2SC)

**Date:** 2026-04-10  
**Status:** Accepted  
**Supersedes:** Parts of ADR 006 (pre-generated phrase library)

## Context

ADR 006 defined a voice system based on pre-generated .wav files and a fixed
phrase library. Initial testing showed the synthesized sounds did not
resemble real R2D2 sounds — the FM parameters were not calibrated against
real reference material.

## Decision

Replace the fixed phrase library with a **generative codec** (R2SC) that the
LLM outputs directly. The codec is calibrated from acoustic analysis of 11
original R2D2 reference recordings.

### Key findings from analysis

| Parameter | Old synth | Real R2D2 | Impact |
|-----------|-----------|-----------|--------|
| FM rate | 8-75 Hz | 3-8 Hz | Old was 10x too fast |
| FM beta | 90-250 | 20-150 | Old was too intense |
| Freq sweep | Small | Up to 3400 Hz | Old sweeps too narrow |
| Sweep + FM | Separate | Simultaneous | Old missed this combination |

The defining R2D2 characteristic is a **slow wobble (3-8 Hz FM) combined
with a wide carrier frequency sweep** — both happening at the same time.

### Architecture change

```
Before: LLM -> intent/emotion -> phrase lookup -> pre-generated WAV
After:  LLM -> R2SC string -> r2sc_synth -> real-time audio
```

The LLM generates codec strings directly, allowing unlimited expressive
variety without any fixed vocabulary.

## Consequences

- No pre-generated .wav files needed (sounds/ directory no longer required)
- LLM must learn R2SC grammar (documented in system prompt)
- Synthesis happens in ~5ms on Pi 4 — negligible latency
- numpy remains the only dependency
- Legacy intent/emotion format still supported via phrase->R2SC fallback table
