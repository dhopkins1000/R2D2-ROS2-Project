#!/bin/bash
# setup_samples.sh — Populate the R2D2 sounds library
#
# This script:
#   1. Creates the sounds/ and sounds/phonemes/ directories
#   2. Copies emotional phrase MP3s from r2d2_sounds/ -> sounds/
#   3. Downloads McGill R2D2 Simulator phoneme WAVs -> sounds/phonemes/
#
# Run from the repo root:
#   bash tools/setup_samples.sh
#
# Dependencies: curl, unzip, ffmpeg (for MP3->WAV conversion if needed)

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOUNDS_DIR="$REPO_ROOT/src/r2d2_audio/sounds"
PHONEMES_DIR="$SOUNDS_DIR/phonemes"
SOURCE_MP3S="$REPO_ROOT/r2d2_sounds"

echo "==> Creating directories"
mkdir -p "$SOUNDS_DIR"
mkdir -p "$PHONEMES_DIR"

# ---------------------------------------------------------------------------
# Step 1: Copy emotional phrase MP3s
# ---------------------------------------------------------------------------
echo "==> Copying phrase samples from r2d2_sounds/"
if [ -d "$SOURCE_MP3S" ]; then
    cp -v "$SOURCE_MP3S"/*.mp3 "$SOUNDS_DIR/" 2>/dev/null && echo "  Done." || echo "  No MP3s found."
else
    echo "  WARNING: r2d2_sounds/ not found. Skipping phrase copy."
fi

# ---------------------------------------------------------------------------
# Step 2: Download McGill R2D2 Simulator phoneme WAVs
# ---------------------------------------------------------------------------
MCGILL_URL="https://www.cs.mcgill.ca/~pkingf/files/R2D2Simulator.zip"
TMP_ZIP="/tmp/R2D2Simulator.zip"

echo "==> Downloading McGill R2D2 Simulator phonemes..."
curl -L "$MCGILL_URL" -o "$TMP_ZIP"
unzip -o "$TMP_ZIP" -d "/tmp/R2D2Simulator/"

PHONEME_WAVS="/tmp/R2D2Simulator/R2D2Simulator/matlab"
echo "==> Copying phoneme WAVs to $PHONEMES_DIR"
for wav in beepybeep.wav berp.wav boop.wav bweep.wav cleanwhistle.wav \
           dwaep.wav dwip.wav dwoop.wav shortgrowl.wav wow.wav; do
    if [ -f "$PHONEME_WAVS/$wav" ]; then
        cp -v "$PHONEME_WAVS/$wav" "$PHONEMES_DIR/"
    else
        echo "  WARNING: $wav not found in ZIP"
    fi
done

rm -f "$TMP_ZIP"

echo ""
echo "==> Setup complete!"
echo "    Phrases:  $(ls $SOUNDS_DIR/*.mp3 2>/dev/null | wc -l) MP3 files"
echo "    Phonemes: $(ls $PHONEMES_DIR/*.wav 2>/dev/null | wc -l) WAV files"
echo ""
echo "Next: colcon build --packages-select r2d2_audio"
