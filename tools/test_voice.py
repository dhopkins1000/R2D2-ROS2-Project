#!/usr/bin/env python3
"""
test_voice.py — Interactive voice system test (no ROS2 required)

Usage:
    python3 tools/test_voice.py --list
    python3 tools/test_voice.py --intent task_complete --emotion excited --intensity high --verbosity 8
    python3 tools/test_voice.py --phrase excited
    python3 tools/test_voice.py --verbosity-sweep   # play same intent at verbosity 1,3,5,7,10
    python3 tools/test_voice.py --all

Dependencies: librosa, soundfile
    pip install librosa soundfile
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "r2d2_audio"))

from r2d2_audio.sample_library import SampleLibrary
from r2d2_audio.utterance_builder import UtteranceBuilder, PLAN_TABLE

DEFAULT_SOUNDS_DIR = str(Path(__file__).parent.parent / "src" / "r2d2_audio" / "sounds")
DEFAULT_ALSA_DEVICE = "plughw:1,0"


def play_audio(wav_bytes: bytes, alsa_device: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp = f.name
    try:
        if sys.platform == "darwin":
            subprocess.run(["afplay", tmp], check=False)
        else:
            subprocess.run(["aplay", "-q", "-D", alsa_device, tmp], check=False)
    finally:
        os.unlink(tmp)


def main():
    parser = argparse.ArgumentParser(description="R2D2 Voice Test")
    parser.add_argument("--sounds_dir", default=DEFAULT_SOUNDS_DIR)
    parser.add_argument("--device", default=DEFAULT_ALSA_DEVICE)
    parser.add_argument("--intent", default="comment")
    parser.add_argument("--emotion", default="excited")
    parser.add_argument("--intensity", default="medium")
    parser.add_argument("--verbosity", type=int, default=5,
                        help="1-10: proportional to LLM response length")
    parser.add_argument("--phrase", help="Play a specific phrase sample directly")
    parser.add_argument("--all", action="store_true",
                        help="Play all plan table entries at verbosity 5")
    parser.add_argument("--verbosity-sweep", action="store_true",
                        help="Play same intent at verbosity 1,3,5,7,10")
    parser.add_argument("--list", action="store_true",
                        help="List available samples")
    args = parser.parse_args()

    print(f"Loading sample library from {args.sounds_dir} ...")
    lib = SampleLibrary(args.sounds_dir)
    builder = UtteranceBuilder(lib)

    if args.list:
        print(f"\nPhrases ({len(lib.available_phrases()):}):")
        for p in sorted(lib.available_phrases()):
            print(f"  {p}")
        print(f"\nPhonemes ({len(lib.available_phonemes()):}):")
        for p in sorted(lib.available_phonemes()):
            print(f"  {p}")
        return

    if args.phrase:
        print(f"Playing phrase: {args.phrase}")
        audio = lib.get_random_phrase_variant(args.phrase)
        if audio is None:
            print(f"  Not found. Available: {lib.available_phrases()}")
            return
        play_audio(lib.render_to_wav_bytes(audio), args.device)
        return

    if args.verbosity_sweep:
        print(f"Verbosity sweep: intent={args.intent} emotion={args.emotion} "
              f"intensity={args.intensity}\n")
        for v in [1, 3, 5, 7, 10]:
            dur_label = {1:"very short",3:"short",5:"medium",7:"long",10:"very long"}
            print(f"  verbosity={v:2d}  ({dur_label[v]})", end=" ", flush=True)
            audio = builder.build(args.intent, args.emotion, args.intensity, v)
            if audio is None:
                print("[no audio]")
            else:
                print(f"[{len(audio)/22050:.2f}s]")
                play_audio(lib.render_to_wav_bytes(audio), args.device)
                time.sleep(0.5)
        return

    if args.all:
        print("Playing all plan table entries at verbosity 5...\n")
        for (intent, modifier), plan in sorted(PLAN_TABLE.items()):
            print(f"  ({intent}, {modifier})" .ljust(38), end=" ", flush=True)
            audio = builder.build(
                intent=intent if intent != "comment" else "comment",
                emotion=modifier if intent == "comment" else "neutral",
                intensity=modifier if intent != "comment" else "medium",
                verbosity=5,
            )
            if audio is None:
                print("[no audio — samples missing]")
            else:
                print(f"[{len(audio)/22050:.2f}s]")
                play_audio(lib.render_to_wav_bytes(audio), args.device)
                time.sleep(0.4)
        return

    # Single play
    print(f"Playing: intent={args.intent} emotion={args.emotion} "
          f"intensity={args.intensity} verbosity={args.verbosity}")
    audio = builder.build(args.intent, args.emotion, args.intensity, args.verbosity)
    if audio is None:
        print("No audio produced. Run --list to check available samples.")
        return
    print(f"  Duration: {len(audio)/22050:.2f}s")
    play_audio(lib.render_to_wav_bytes(audio), args.device)


if __name__ == "__main__":
    main()
