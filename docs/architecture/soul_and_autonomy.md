# R2D2 Soul & Autonomy — Architecture

> **Status:** Partially implemented — see roadmap below for current state
> **Author:** Daniel Hopkins

---

## Motivation

A robot that only reacts to commands is a remote control car with extra steps.
The goal is to give R2D2 a **persistent character**, **autonomous decision-making**,
and **initiative** — so that he feels like a presence in the room rather than a
machine waiting for instructions.

---

## Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         SENSORS                             │
│   SRF02 · Depth Camera · Mic Array · Encoders · Compass     │
└──────────────────────────┬──────────────────────────────────┘
                           │ ROS2 Topics
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         LAYER 1 — REACTIVE  ✔ Implemented (chassis)         │
│                                                             │
│  Fast, deterministic, safety-critical. No LLM.              │
│  • SRF02 detects drop → emergency stop                      │
│  • Obstacle < 20cm → halt + backoff                         │
│  • Wake word detected → head turns to DOA direction         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         LAYER 2 — DELIBERATIVE  ⧠ Planned (post-Nav2)      │
│                                                             │
│  Behavior Trees via py_trees_ros                            │
│  Fallback                                                   │
│  ├── Voice command pending? → execute speech action          │
│  ├── Battery low?           → navigate to charger            │
│  ├── Mood.curiosity high?   → approach novel object          │
│  ├── Mood.boredom high?     → seek human presence            │
│  └── Default               → autonomous exploration          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         LAYER 3 — CHARACTER  ✔ Implemented                  │
│                                                             │
│  mood_node   — publishes /r2d2/mood @ 1Hz, persists to disk │
│  memory_node — SQLite episodic log + place annotations      │
│                                                             │
│  Mood vector:                                               │
│    energy:    0.0–1.0  → maps from battery level            │
│    curiosity: 0.0–1.0  → spikes on novelty, decays slowly   │
│    boredom:   0.0–1.0  → rises with inactivity              │
│    social:    0.0–1.0  → spikes after interaction           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         LAYER 4 — LLM REASONING  ✔ Implemented             │
│                                                             │
│  context_builder_node — assembles mood+memory into prompt   │
│  llm_node             — calls gemini-cli, returns JSON      │
│                                                             │
│  Triggers:                                                  │
│    a) /r2d2/llm_trigger (voice/STT input)                   │
│    b) autonomous when boredom > 0.8 (every 5min min.)       │
└─────────────────────────────────────────────────────────────┘
```

---

## ROS2 Node Map (current implementation)

| Node | Package | Publishes | Subscribes |
|---|---|---|---|
| `mood_node` | `r2d2_soul` | `/r2d2/mood` | `/r2d2/events` |
| `memory_node` | `r2d2_soul` | `/r2d2/memory_summary` | `/r2d2/events` |
| `context_builder_node` | `r2d2_soul` | `/r2d2/llm_input`, `/r2d2/events` | `/r2d2/mood`, `/r2d2/memory_summary`, `/r2d2/llm_trigger` |
| `llm_node` | `r2d2_soul` | `/r2d2/llm_response`, `/r2d2/llm_busy` | `/r2d2/llm_input` |
| `behavior_tree_node` | `r2d2_soul` | `/cmd_vel`, `/r2d2/speech_out` | `/r2d2/llm_response`, `/r2d2/mood` |

---

## Topic Naming — Two LLM Input Paths

There are two ways to get a prompt into the LLM. Understanding the difference is important:

### Path A — `/r2d2/llm_trigger` (recommended for normal use)

```
/r2d2/llm_trigger
       │  (raw text: STT output or manual input)
       ▼
context_builder_node
       │  enriches prompt with:
       │  • current mood vector
       │  • time since last interaction
       │  • recent episodic memory
       │  • known places
       ▼
/r2d2/llm_input
       │  (full context prompt)
       ▼
llm_node (gemini-cli)
       │
       ▼
/r2d2/llm_response
```

Use this path for:
- STT output from the voice pipeline
- Manual testing: `ros2 topic pub --once /r2d2/llm_trigger ...`
- Autonomous boredom trigger (context_builder fires this internally)

### Path B — `/r2d2/llm_input` (bypass, for debugging only)

```
/r2d2/llm_input  →  llm_node  →  /r2d2/llm_response
```

Byasses context enrichment. R2D2 responds without mood/memory context.
Only use for testing the LLM node in isolation.

---

## LLM Backend

**Current implementation:** gemini-cli (`google-gemini/gemini-cli`)

| Aspect | Detail |
|---|---|
| Binary | `gemini` (npm install -g @google/gemini-cli) |
| Auth | `GOOGLE_API_KEY` env var (aistudio.google.com, free tier) |
| Model | `gemini-2.5-flash` (default, configurable) |
| Free quota | 15 req/min, 1500 req/day — sufficient for R2D2 |
| Soul context | `GEMINI.md` in `/home/r2d2/soul/` loaded automatically |
| Invocation | `subprocess.run(['gemini', '-p', prompt, '--output-format', 'json', ...])` |
| Latency | ~15–20s cold, improves with prompt caching |

The `llm_node` is backend-agnostic by design. Gemini was chosen over Claude Code
(Node.js startup overhead, same latency) and the raw Google AI Python SDK
(lacks built-in tool calls, web search, MCP support for future use).

---

## Mood System

See `src/r2d2_soul/r2d2_soul/mood_node.py` for implementation.

```
Decay rules (per second):
  boredom   += 0.001      (rises during inactivity)
  boredom    = 0.0        (reset on interaction event)
  curiosity → rest=0.3   (slow decay)
  social    → rest=0.1   (faster decay)
  energy     = battery    (direct mapping via battery event)
```

State persists across reboots: `/home/r2d2/soul/state/mood.json`

---

## Memory System

See `src/r2d2_soul/r2d2_soul/memory_node.py` for implementation.

SQLite database: `/home/r2d2/.r2d2/memory.db`

```sql
CREATE TABLE events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  type      TEXT NOT NULL,  -- interaction|exploration|observation|navigation|novel_object
  location  TEXT DEFAULT '',
  summary   TEXT DEFAULT ''
);

CREATE TABLE places (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  label     TEXT NOT NULL UNIQUE,  -- "daniel_desk", "kitchen", "charging_dock"
  x         REAL DEFAULT 0.0,      -- SLAM coordinates (populated once Nav2 is operational)
  y         REAL DEFAULT 0.0,
  last_seen TEXT DEFAULT ''
);
```

Any node can publish to `/r2d2/events` to log an event.
The `places` table is pre-created and ready; coordinates populated once SLAM is available.

---

## Context Prompt Example

The `context_builder_node` produces prompts like this:

```
Current mood:
  energy=0.45  curiosity=0.61  boredom=0.33  social=0.53
Time since last interaction: 3 minute(s)

Recent memory (last 3 of 5 events):
  2026-04-24 00:06 [living_room] — Daniel fragte nach dem Status
  2026-04-24 00:07 [kitchen] — Detected a novel object
  2026-04-24 00:08 — Voice interaction occurred
Known places: living_room, kitchen

Daniel just said: "Was hast du heute so gemacht?"
Respond in character as R2D2.
```

---

## LLM Output Schema

All responses from `llm_node` conform to this JSON structure:

```json
{
  "goal": "idle | speak | navigate_to | explore | dock | stop | turn_head | head_scan",
  "goal_params": {},
  "utterance": {
    "intent": "<beep_intent or null>",
    "intensity": 0.5
  },
  "lcd": {
    "line1": "<max 40 chars>",
    "line2": "<max 40 chars>"
  },
  "mood_delta": {
    "curiosity": 0.0,
    "boredom": 0.0,
    "social": 0.0
  },
  "memory_write": null,
  "internal_note": null,
  "_meta": {
    "latency_s": 17.6,
    "model": "gemini-2.5-flash",
    "total_tokens": 13902,
    "cached_tokens": 12923
  }
}
```

The `mood_delta` from the response is published back to `/r2d2/events` so the
`mood_node` can update the emotional state accordingly.

---

## Implementation Roadmap

### Phase 1 — Foundation
- [x] Create `r2d2_soul` ROS2 package
- [x] Implement `mood_node` with decay rules and state persistence
- [ ] Implement minimal behavior tree — *waiting for Nav2*

### Phase 2 — Memory
- [x] Implement `memory_node` with SQLite backend (events + places)
- [x] Publish events from existing nodes
- [x] Persistence across reboots verified

### Phase 3 — LLM Integration
- [x] Implement `context_builder_node`
- [x] Implement `llm_node` with gemini-cli backend
- [x] Autonomous boredom trigger wired
- [ ] Wire STT output → `/r2d2/llm_trigger` — *voice node deferred*

### Phase 4 — Autonomous Initiative
- [x] Boredom threshold → autonomous LLM trigger (5min min. interval)
- [ ] Tune mood decay parameters once R2D2 is mobile
- [ ] Ollama as offline fallback backend — *deferred*

### Phase 5 — Character Tuning
- [x] GEMINI.md soul context file
- [x] Beep language intent list enforced via GEMINI.md
- [ ] Wire `mood_delta` from LLM response back to `mood_node` via events
- [ ] Long-term memory summarization

### Phase 6 — Behavior Tree + Navigation
- [ ] Implement behavior tree node (`py_trees_ros`)
- [ ] Wire `goal` from LLM response → Nav2 goals
- [ ] SLAM semantic place labeling
- [ ] Autonomous dock navigation

### Phase 7 — Voice Pipeline
- [ ] Mic test: ReSpeaker vs. USB webcam quality comparison
- [ ] faster-whisper STT node
- [ ] Wire wake word → record → STT → `/r2d2/llm_trigger`

---

## Open Questions

1. **Map semantic labeling:** How does R2D2 learn place names? Manual config vs. asking via speech?
2. **Camera data in LLM context:** Should object detection labels be included? Privacy consideration.
3. **Safety ADR:** Reactive layer must be fully independent of soul layer — document as ADR.
4. **mood_delta feedback loop:** LLM response contains `mood_delta` — needs to be published to `/r2d2/events` so `mood_node` applies it. Not yet wired.

---

## Related Documents

- `docs/architecture/voice_pipeline.md` — STT and voice input architecture
- `docs/setup/autostart.md` — systemd autostart setup
- `docs/decisions/` — ADRs
- `R2D2-Soul` repository — GEMINI.md, SOUL.md, MEMORY.md etc.
