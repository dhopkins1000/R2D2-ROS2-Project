# Tools

## analyze_r2d2_sounds.py

Analyzes original R2D2 MP3 reference files and extracts acoustic parameters
for designing the R2D2 Sound Codec (R2SC).

### Setup

```bash
pip install librosa numpy scipy soundfile matplotlib
```

### Usage

```bash
# Analyze all files in r2d2_sounds/
python3 tools/analyze_r2d2_sounds.py --sounds_dir r2d2_sounds/

# Single file
python3 tools/analyze_r2d2_sounds.py --file r2d2_sounds/excited.mp3

# With spectrogram plots
python3 tools/analyze_r2d2_sounds.py --sounds_dir r2d2_sounds/ --plot
```

### Output

Creates `analysis/` directory containing:
- `<name>.json` — per-file extracted parameters
- `<name>_spectrogram.png` — spectrogram with F0 overlay (if `--plot`)
- `summary.json` — all files combined, share this for codec design

### What it extracts

For each discrete sound event within a file:
- Dominant frequency (start, end, mean)
- Frequency trajectory (sweep up/down/stable/complex)
- FM modulation rate and depth
- FM character classification (vibrato / wobble / trill / buzz)
- Attack and release times
- Peak amplitude

The script also generates a rough **R2SC codec sketch** per file —
a compact text representation of the sound that becomes the basis
for the full codec the LLM will use to generate sounds on-the-fly.
