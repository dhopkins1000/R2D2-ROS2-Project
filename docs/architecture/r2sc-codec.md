# R2D2 Sound Codec (R2SC)

A compact text language for describing R2D2 sounds.
Derived from acoustic analysis of 11 original R2D2 reference recordings.

## Grammar

An utterance is a sequence of segments separated by ` | `:

| Type | Syntax | Description |
|------|--------|-------------|
| `W`  | `W<f0>-<f1>:<fm>:<beta>:<dur>` | Wobble with carrier sweep |
| `W`  | `W<fc>:<fm>:<beta>:<dur>` | Wobble at stable pitch |
| `S`  | `S<f0>-<f1>:<dur>` | Pure frequency sweep |
| `C`  | `C<fc>:<dur>` | Chirp (short pure tone) |
| `T`  | `T<fc>:<fm>:<dur>` | Trill (fast FM, beta=150) |
| `~`  | `~<dur>` | Silence gap |

All frequencies in **Hz**, durations in **seconds**.

## Parameter ranges (from reference analysis)

| Parameter | Range | Notes |
|-----------|-------|-------|
| `fc`, `f0`, `f1` | 150 – 3200 Hz | Carrier frequency |
| `fm` (wobble) | 3 – 8 Hz | Slow emotional warble |
| `fm` (trill) | 35 – 65 Hz | Fast excitement/alarm |
| `beta` | 20 – 150 | FM depth. 20=subtle, 150=intense |
| `dur` | 0.05 – 4.0 s | Per segment |

## Semantic patterns (from reference sounds)

| Emotion | Carrier range | Sweep | Beta | fm rate |
|---------|--------------|-------|------|--------|
| Acknowledged | 1190-1364 Hz | small up | 21 | 8 Hz |
| Curious | stable ~1340 Hz + rising wobble | up | 42 | 3 Hz |
| Surprised | 975-2278 Hz | big up | 76 | 4 Hz |
| Excited | 1300-2167 Hz | up | 96-126 | 4-5 Hz |
| Concerned | 1008-1796 Hz | up | 85 | 4 Hz |
| Worried | 585-945 Hz | up (low range) | 136 | 3 Hz |
| Chat | 1953-2476 Hz | up (high range) | 27 | 4 Hz |

**Rules of thumb:**
- High carrier (1500-3200 Hz) = positive / excited
- Low carrier (150-800 Hz) = negative / worried / sad
- Rising sweep = questioning / curious / surprised
- Falling sweep = sad / finished / resigned
- High beta (100+) = strong emotion
- Low beta (20-40) = calm / subtle
- fm 7-8 Hz = R2D2's distinctive quick warble
- fm 3-4 Hz = slower, more emotional

## Reference codec strings

```
acknowledged:  W1190-1364:8:21:0.42 | C681:0.07
surprised:     W975-2278:4:76:0.65
worried:       W585-945:3:136:1.01
curious:       C1344:0.27 | W1131-1359:3:42:0.41
concerned:     W1008-1796:4:85:2.05
excited:       W1300-2167:5:96:0.93
excited (big): W1300-1531:4:126:1.99
chat:          W1953-2476:4:27:1.02
chat (long):   W2498-2051:3:54:2.0
```

## LLM integration

Include this in R2D2's system prompt:

```
When R2D2 should react vocally, include a "voice" key:

{
  "voice": {
    "speak": true,
    "r2sc": "<codec string>"
  }
}

R2SC grammar — segments separated by " | ":
  W<f0>-<f1>:<fm>:<beta>:<dur>   wobble with sweep  (most expressive)
  W<fc>:<fm>:<beta>:<dur>        wobble stable pitch
  S<f0>-<f1>:<dur>               pure sweep
  C<fc>:<dur>                    chirp
  T<fc>:<fm>:<dur>               trill (excitement/alarm)
  ~<dur>                         silence

Parameter ranges:
  frequency:  150-3200 Hz
  fm (wobble): 3-8 Hz   |   fm (trill): 35-65 Hz
  beta:       20-150
  duration:   0.05-4.0 s  (total utterance ideally under 3s)

Semantic guide:
  HIGH freq (1500-3200) = positive/excited
  LOW freq  (150-800)   = negative/worried/sad
  RISING sweep          = question/surprise/curiosity
  FALLING sweep         = sad/done/resigned
  HIGH beta (100+)      = strong emotion
  LOW beta  (20-40)     = calm/subtle

Reference examples:
  Happy/done:    W1190-1364:8:21:0.42 | C1600:0.08
  Surprised:     W975-2278:4:76:0.65
  Worried:       W585-945:3:136:1.01
  Curious:       C1344:0.27 | W1131-1359:3:42:0.41
  Excited:       W1300-2167:5:96:0.93
  Warning:       C1950:0.14 | ~0.04 | C1950:0.14 | ~0.04 | W340:75:56:0.28
  Thinking:      W740:5:18:0.80 | ~0.08 | C920:0.08
  Sad/failed:    W720-480:5:56:0.80 | S1200-400:0.35

Set speak=false if no vocal reaction is needed.
Max 4 segments per utterance. Total duration ideally under 3 seconds.
```

## Files

| File | Purpose |
|------|---------|
| `src/r2d2_audio/r2d2_audio/r2sc_synth.py` | Parser + FM synthesizer |
| `src/r2d2_audio/r2d2_audio/voice_node.py` | ROS2 node (uses r2sc_synth) |
| `tools/analyze_r2d2_sounds.py` | Analysis script used to calibrate the codec |
| `r2d2_sounds/` | Original R2D2 reference MP3 files |
