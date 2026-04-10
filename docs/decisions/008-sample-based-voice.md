# ADR 008: Sample-Based Voice System

**Date:** 2026-04-10  
**Status:** Accepted  
**Supersedes:** ADR 006, ADR 007 (FM synthesis / R2SC codec)

## Context

ADR 006 and ADR 007 defined FM synthesis approaches (R2SC codec) to
generatively create R2D2 sounds. Testing confirmed these sounded
unconvincing despite careful parameter calibration from real recordings.

Research into Human-Cyborg Relations (Michael Perl, Stanford) established
the fundamental reason: R2D2's voice is organic, analog, and hand-curated.
Ben Burtt used an ARP 2600 analog synthesizer and his own voice, recorded
to tape. These qualities cannot be reproduced by digital FM synthesis.

## Decision

Switch to a **sample-based voice system** using original R2D2 recordings
as building blocks, combined with real-time pitch shifting and time
stretching for variation.

### Two-tier architecture

**Tier 1 — Emotional phrases** (`r2d2_sounds/*.mp3`):  
Full utterances with a specific emotional label. Played directly with
small pitch/speed variation (±1.5 semitones, ±7%) for naturalness.
Used for strong, contextually clear emotional moments.

**Tier 2 — Generative phoneme sequencing** (`sounds/phonemes/*.wav`):  
Micro-samples (0.1-0.8s) from McGill R2D2 Simulator, organized into
semantic categories (bump, tone, whistle, systle, reeo, birdsong, growl).
Chained 2-4 at a time with pitch shift per segment for emotional register.
Used for varied, ambient, or functional utterances.

### Why this approach

- Sample quality is authentic by definition — these are original recordings
- Pitch shifting + time stretching creates natural variation without
  synthesizing new sounds (same technique used by H-CR and original Lucasfilm)
- Falls back gracefully: if Tier 1 phrases are unavailable, Tier 2 generates
  a reasonable substitute from phonemes alone

## Consequences

- Requires librosa and soundfile Python packages on the Pi
- ~1-3s startup time to load samples into memory
- `tools/setup_samples.sh` must be run once to populate the sounds directory
- The sounds/ directory is git-ignored (binary audio files)
- FM synthesizer (r2sc_synth.py) is retained in feature/r2d2-sound-codec
  as a reference implementation / proof of concept
