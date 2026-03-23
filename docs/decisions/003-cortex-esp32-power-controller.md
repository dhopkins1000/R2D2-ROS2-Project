# ADR 003 – Cortex ESP32 as Power Controller

## Status
Proposed

## Context
R2D2 needs to run on battery (12V) for ≥4h.
Idle periods should consume minimal power.
The Pi cannot safely cut its own power.

## Decision
Add a dedicated "Cortex" ESP32 as an always-on power controller.

## Reasons
- ESP32 deep sleep draws ~0.05W vs Pi idle at ~3W
- Pi cannot safely cut its own power supply
- Cortex can monitor Pi GPIO shutdown signal and cut power after safe shutdown
- Cortex can receive wake signals (wake word, timer, button) and boot the Pi
- Watchdog: if Pi heartbeat topic stops, Cortex can trigger reboot
- Single point of control for all power relays

## Implementation Plan
- Cortex ESP32 controls:
  - Relay 1: 12V to MD25
  - Relay 2: 5V to Powered USB Hub
  - 5V to Pi (via relay or controlled enable pin)
- Pi GPIO (e.g. GPIO 26) goes low on shutdown → Cortex detects and cuts power
- Wake sources: ReSpeaker wake word signal, physical button, RTC timer

## Consequences
- Extra ESP32 board needed
- Power sequencing logic must be robust
- Risk: if Cortex firmware crashes, R2D2 is stuck (needs physical reset)
- Mitigation: hardware watchdog on Cortex itself
