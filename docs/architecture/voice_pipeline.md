# R2D2 Voice Input Pipeline — Architecture

> **Status:** Concept / Future Work  
> **Depends on:** Wake word node (openWakeWord, already implemented)  
> **Part of:** Soul & Autonomy layer (`r2d2_soul` package)  

---

## Overview

The voice pipeline turns a detected wake word into a structured action decision. It is the primary interactive path into the soul layer.

```
 ReSpeaker Mic Array
        │
        ▼
  wake_word_node          ← already implemented (openWakeWord)
  publishes: /r2d2/wake_word_detected
        │
        ▼
  voice_input_node        ← arms mic, records until silence
  publishes: /r2d2/audio_clip  (raw WAV bytes)
        │
        ▼
  whisper_stt_node        ← faster-whisper, local on Pi
  publishes: /r2d2/transcript  (string)
        │
        ▼
  intent_router_node      ← classify: BT-handleable or LLM-needed?
  publishes: /r2d2/intent  or  /r2d2/llm_trigger
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
  behavior_tree_node               llm_node
  (handles simple intents)         (handles complex / conversational)
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
              output_router_node
              publishes:
                /r2d2/lcd_text      → SerLCD 40x2 at head
                /r2d2/utterance     → beep language synthesizer
                /r2d2/llm_goal      → behavior tree for physical action
```

---

## Microphone: ReSpeaker V1.0 (not Webcam, not Xtion)

The ReSpeaker Mic Array V1.0 is already the audio hardware — it stays the only mic for voice input. No testing of alternatives is needed:

| Device | Far-field quality | Notes |
|---|---|---|
| **ReSpeaker V1.0** | ✅ Designed for it | 4-mic array, already used for wake word |
| USB Webcam | ❌ Poor | Single omnidirectional mic, noisy |
| ASUS Xtion Pro | ❌ N/A | Has **no microphone** — depth