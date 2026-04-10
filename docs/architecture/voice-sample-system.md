# R2D2 Sample-Based Voice System

## Why samples, not synthesis

Research by Human-Cyborg Relations (Michael Perl, 2020) established that
R2D2's voice cannot be convincingly reproduced by digital FM synthesis.
The original sounds were produced by Ben Burtt using:
- His own voice
- An ARP 2600 analog synthesizer (LFO-modulated self-oscillating filter)
- Tape recording and manual editing

The organic, analog character of these sounds is impossible to replicate
digitally. The only way to produce authentic R2D2 speech is to repurpose
original recordings as building blocks.

## Architecture

```
LLM JSON output
  { "speak": true, "intent": "task_complete", "emotion": "excited", "intensity": "high" }
          |
          v
  voice_node.py  (ROS2, /r2d2/voice_intent)
          |
          v
  utterance_builder.py
    Tier 1: PhrasePlan  ──►  direct emotional phrase sample
    Tier 2: GenerativePlan  ──►  chained phoneme sequence
          |
          v
  sample_library.py
    - librosa pitch shift (±1.5 semitones)
    - librosa time stretch (±7% speed)
          |
          v
  aplay (Linux) / afplay (macOS)
```

## Sample library structure

```
src/r2d2_audio/sounds/
    excited.mp3          <- Tier 1: emotional phrase samples
    worried.mp3
    curious.mp3
    acknowledged.mp3
    ... (11 files total)
    phonemes/            <- Tier 2: micro-phoneme WAVs
        boop.wav         <- bump category
        berp.wav         <- tone category
        dwip.wav         <- tone category
        cleanwhistle.wav <- whistle category
        bweep.wav        <- systle category
        dwaep.wav        <- reeo category
        dwoop.wav        <- reeo category
        wow.wav          <- reeo category
        beepybeep.wav    <- birdsong category
        shortgrowl.wav   <- growl category
```

Phoneme WAVs are sourced from the McGill R2D2 Simulator (P. Kingford, 2013).
Setup script: `tools/setup_samples.sh`

## Phoneme categories (HCR-inspired)

| Category  | Files          | Character                |
|-----------|----------------|--------------------------|
| bump      | boop           | Soft low boop            |
| tone      | berp, dwip     | Single beep/dip          |
| whistle   | cleanwhistle   | Organic rising whistle   |
| systle    | bweep          | Synthetic sweep up       |
| reeo      | dwaep, dwoop, wow | Complex sweeping tones|
| birdsong  | beepybeep      | Multi-tone chitter       |
| growl     | shortgrowl     | Low mechanical growl     |

## Emotional semantics (from HCR research)

| Emotion   | Register  | Categories preferred        |
|-----------|-----------|-----------------------------|
| Excited   | High      | birdsong, whistle, reeo     |
| Happy     | High      | whistle, birdsong, tone     |
| Curious   | Mid       | tone, systle, reeo          |
| Sad       | Low       | growl, reeo (slow)          |
| Worried   | Low       | tone, growl, reeo           |
| Angry     | Low       | growl, bump, growl          |

Key HCR insight: R2 is afraid ~75% of the time. Fear + excitement
(high-pitch + fast) is the most common emotional combination.
Pitch up = positive, pitch down = negative/worried.

## Variation mechanism

Every playback applies small random variation to avoid repetition:
- Pitch shift: ±1.5 semitones (phrase), ±2.0 semitones (phoneme)
- Speed: ±7% (phrase)
- Phoneme selection: random from category pool

This mirrors the H-CR approach where slight pitch/timing variations
are derived from film analysis of how Ben Burtt reused sounds.

## Setup

```bash
# Populate sample library (run once)
bash tools/setup_samples.sh

# Install Python deps
pip install librosa soundfile

# Test without ROS2
python3 tools/test_voice.py --list
python3 tools/test_voice.py --intent greeting --emotion excited --intensity high
python3 tools/test_voice.py --all

# Build and run in ROS2
cd ~/ros2_ws && colcon build --packages-select r2d2_audio
source install/setup.bash
ros2 run r2d2_audio voice_node
```

## ROS2 topics

| Topic                 | Type            | Direction | Description          |
|-----------------------|-----------------|-----------|----------------------|
| /r2d2/voice_intent    | std_msgs/String | sub       | LLM intent JSON      |
| /r2d2/voice_playing   | std_msgs/String | pub       | Playback status      |
