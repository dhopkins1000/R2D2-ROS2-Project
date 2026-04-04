# R2D2 Soul & Autonomy — Architecture Concept

> **Status:** Concept / Future Work  
> **Target:** Implement after chassis wiring and basic navigation are stable  
> **Author:** Daniel Hopkins  

---

## Motivation

A robot that only reacts to commands is a remote control car with extra steps. The goal of this document is to define an architecture that gives R2D2 a **persistent character**, **autonomous decision-making**, and **initiative** — so that he feels like a presence in the room rather than a machine waiting for instructions.

The core idea: layer reactive reflexes, deliberate goal-setting, and a mood-influenced character on top of the existing ROS2 infrastructure, with an LLM as the reasoning engine for high-level decisions.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         SENSORS                             │
│   SRF02 · Depth Camera · Mic Array · Encoders · Compass     │
└──────────────────────────┬──────────────────────────────────┘
                           │ ROS2 Topics
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              LAYER 1 — REACTIVE (Reflexes)                  │
│                                                             │
│  Fast, deterministic, safety-critical.                      │
│  No LLM. No behavior tree. Pure sensor → action.            │
│                                                             │
│  Examples:                                                  │
│  • SRF02 detects drop → emergency stop                      │
│  • Obstacle < 20cm → halt + backoff                         │
│  • Wake word detected → head turns to DOA direction         │
└──────────────────────────┬──────────────────────────────────┘
                           │ Safety signals
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            LAYER 2 — DELIBERATIVE (Behavior Trees)          │
│                                                             │
│  What does R2D2 do right now, given goals and context?      │
│  Implemented via py_trees_ros or BehaviorTree.CPP           │
│                                                             │
│  Fallback                                                   │
│  ├── Voice command pending?     → execute speech action     │
│  ├── Battery low?               → navigate to charger       │
│  ├── Mood.curiosity high?       → approach novel object     │
│  ├── Mood.boredom high?         → seek human presence       │
│  └── Default                   → autonomous exploration     │
│                                                             │
│  Reads from: /r2d2/mood, /r2d2/llm_goal, /r2d2/memory      │
└──────────────────────────┬──────────────────────────────────┘
                           │ Nav2 goals / speech commands
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              LAYER 3 — CHARACTER (Mood & Memory)            │
│                                                             │
│  Persistent state that colors all decisions.                │
│                                                             │
│  /r2d2/mood (published continuously):                       │
│    energy:    0.0–1.0  → affects movement speed             │
│    curiosity: 0.0–1.0  → exploration bias                   │
│    boredom:   0.0–1.0  → rises over time, triggers init.    │
│    social:    0.0–1.0  → spikes after interaction           │
│                                                             │
│  /r2d2/memory (SQLite, persists across reboots):            │
│    • Episodic log: what happened, when, where               │
│    • Spatial map annotations ("Daniel's desk", "kitchen")   │
│    • Interaction history                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Context summary
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               LAYER 4 — LLM REASONING ENGINE                │
│                                                             │
│  High-level goal generation. Triggered:                     │
│    a) by wake word + speech input (interactive)             │
│    b) periodically when boredom threshold exceeded          │
│    c) on significant environmental change                   │
│                                                             │
│  Input: structured context prompt (see below)               │
│  Output: JSON → goal + utterance + mood_delta               │
│                                                             │
│  LLM options: Anthropic API (remote) or Ollama (local)      │
└─────────────────────────────────────────────────────────────┘
```

---

## ROS2 Node Map

| Node | Package | Topics Published | Topics Subscribed |
|---|---|---|---|
| `mood_node` | `r2d2_soul` | `/r2d2/mood` | `/r2d2/events` |
| `memory_node` | `r2d2_soul` | `/r2d2/memory_summary` | `/r2d2/events` |
| `context_builder_node` | `r2d2_soul` | `/r2d2/llm_context` | `/r2d2/mood`, `/r2d2/memory_summary`, sensor topics |
| `llm_node` | `r2d2_soul` | `/r2d2/llm_goal` | `/r2d2/llm_context` |
| `behavior_tree_node` | `r2d2_soul` | `/cmd_vel`, `/r2d2/speech_out` | `/r2d2/llm_goal`, `/r2d2/mood`, nav2 |

All of these live in a new package: **`r2d2_soul`**.

---

## Mood System — Detail

The mood is a simple ROS2 node that maintains a float vector and publishes it at ~1Hz. Mood values change based on events:

```python
# Mood decay / drift rules (approximate)
boredom    += 0.001 per second of inactivity   # gets bored slowly
boredom     = 0.0   on any interaction          # reset on interaction
curiosity  += spike on novel object detected
curiosity  -= 0.0005 per second (decays)
social     += spike on voice interaction
social     -= 0.001 per second (decays)
energy      = fn(battery_level)                 # direct mapping
```

Mood influences behavior tree priorities and LLM prompts — it does **not** bypass safety constraints.

---

## LLM Context Prompt — Example

The `context_builder_node` assembles a structured natural language prompt and sends it to the `llm_node`:

```
You are R2D2. You are a small, loyal, expressive droid.
You do not speak in full sentences — you beep, whistle, and occasionally blurt short phrases.

Current state:
- Location: living room, near couch
- Observed: Daniel is at his desk, looking at a screen
- Time since last interaction: 47 minutes
- Mood: curiosity=0.7, boredom=0.8, social=0.3, energy=0.9
- Recent events: explored kitchen 30min ago, found nothing new
- Battery: 82%

Recent memory (last 3 events):
1. 14:03 — Daniel said "hey R2" and asked about the weather
2. 13:45 — Explored hallway, detected no obstacles
3. 13:12 — Docked at charging station

What do you do next? Respond ONLY with valid JSON:
{
  "goal": "navigate_to|speak|explore|idle|dock",
  "goal_params": {},
  "utterance": "short R2D2-style sound or phrase, or null",
  "mood_delta": {"curiosity": 0.0, "boredom": 0.0, "social": 0.0}
}
```

---

## LLM Backend Options

| Option | Latency on Pi 4 | Privacy | Quality | Recommended for |
|---|---|---|---|---|
| **Anthropic API** (claude-haiku) | ~1–2s | Data leaves network | High | Development, interactive use |
| **Ollama + Llama 3.2 3B** | ~8–15s | Fully local | OK for simple goals | Offline / autonomous mode |
| **Ollama + Qwen2.5 1.5B** | ~4–8s | Fully local | Lower | Fallback if latency matters |

**Recommended approach:** Start with Anthropic API. Add Ollama as offline fallback later.

The `llm_node` should be backend-agnostic — swap via config parameter.

---

## Memory System — Detail

SQLite database at `~/.r2d2/memory.db`, managed by `memory_node`.

```sql
-- Episodic memory
CREATE TABLE events (
  id        INTEGER PRIMARY KEY,
  timestamp TEXT,
  type      TEXT,   -- 'interaction' | 'exploration' | 'observation' | 'navigation'
  location  TEXT,   -- semantic label from map annotations
  summary   TEXT    -- one-line description
);

-- Spatial annotations
CREATE TABLE places (
  id        INTEGER PRIMARY KEY,
  label     TEXT,   -- "Daniel's desk", "kitchen", "charging dock"
  x         REAL,
  y         REAL,
  last_seen TEXT
);
```

The `memory_node` subscribes to a `/r2d2/events` topic — any node can publish events. The `context_builder_node` queries the last N events to include in the LLM prompt.

---

## Behavior Tree — Minimal First Implementation

```
Root (Fallback)
├── Sequence: Safety
│   ├── Is reactive layer healthy? (always checked first)
│   └── Is nav2 active?
│
├── Sequence: Command pending
│   ├── Is there a pending LLM goal?
│   └── Execute goal (navigate / speak / explore)
│
├── Sequence: Low battery
│   ├── Battery < 20%?
│   └── Navigate to dock
│
├── Sequence: High boredom
│   ├── mood.boredom > 0.8?
│   └── Trigger LLM for autonomous goal
│
└── Action: Idle (slow spin, look around)
```

Package recommendation: **`py_trees_ros`** (Python, easier to prototype; can be replaced with `BehaviorTree.CPP` for performance later)

---

## Implementation Roadmap

### Phase 1 — Foundation (no LLM yet)
- [ ] Create `r2d2_soul` ROS2 package
- [ ] Implement `mood_node` with basic decay rules
- [ ] Implement minimal behavior tree (idle + explore)
- [ ] Test: R2D2 wanders autonomously, respects safety layer

### Phase 2 — Memory
- [ ] Implement `memory_node` with SQLite backend
- [ ] Publish events from existing nodes (audio, navigation)
- [ ] Verify persistence across reboots

### Phase 3 — LLM Integration
- [ ] Implement `context_builder_node`
- [ ] Implement `llm_node` with Anthropic API backend
- [ ] Wire wake word → LLM trigger
- [ ] Test interactive conversations with goal output

### Phase 4 — Autonomous Initiative
- [ ] Wire boredom threshold → LLM trigger
- [ ] Tune mood decay parameters for natural rhythm
- [ ] Add Ollama as offline fallback backend

### Phase 5 — Character Tuning
- [ ] Refine system prompt for authentic R2D2 character
- [ ] Add R2D2 sound synthesis (beeps, whistles) to utterance output
- [ ] Long-term memory summarization (compress old events)

---

## Dependencies

```bash
# Behavior Trees
pip install py_trees py_trees_ros

# LLM (remote)
pip install anthropic

# LLM (local, optional)
# Install Ollama separately: https://ollama.ai
pip install ollama

# Memory
# sqlite3 is part of Python stdlib — no install needed
```

---

## Open Questions (to decide during implementation)

1. **Map semantic labeling:** How does R2D2 learn place names? Manual config vs. asking the user via speech?
2. **LLM trigger rate:** How often should R2D2 autonomously check if he wants to do something? Every 5min? Driven purely by boredom threshold?
3. **Character voice:** Text-to-speech (piper-tts) with R2D2 audio processing, or pure sound synthesis (beeps/boops)? Or both?
4. **Privacy:** Should the LLM context ever include camera data (object detection labels)? Needs explicit consideration before implementing.
5. **Safety boundary:** The reactive layer must be completely independent of the soul layer. Soul layer cannot override safety stops. Document this as an ADR.

---

## Related Documents

- `docs/architecture/system_overview.md` — overall ROS2 node graph
- `docs/decisions/` — ADRs for key decisions
- `docs/hardware/` — hardware inventory and wiring plans
