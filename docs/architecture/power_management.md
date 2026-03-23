# Power Management Architecture

## Requirements
- Battery: 12V
- Target runtime: ≥ 4h active, longer in idle
- Ability to power down unused subsystems
- Safe shutdown sequence
- Automatic wake from idle

## Power Budget Estimate

| Component | Idle | Active | Notes |
|---|---|---|---|
| Raspberry Pi 4 | 3W | 5W | |
| Chassis ESP32 | 0.1W | 0.2W | |
| Head ESP32 | 0.1W | 0.2W | Bluetooth |
| Cortex ESP32 | 0.05W | 0.05W | Always on |
| ASUS Xtion Pro | 1W | 2.5W | Can be powered off |
| USB Webcam | 0.5W | 0.5W | Can be powered off |
| ReSpeaker Mic Array | 0.5W | 1W | Low power listen mode possible |
| Powered USB Hub | 0.5W | 1W | Switchable |
| MD25 + Motors | 0W | 10–20W | Only when driving |
| SSD1306 OLED | 0.1W | 0.1W | |
| SerLCD + RGB Matrix | 0.2W | 0.5W | |
| **Total** | **~6W** | **~30W** | excl. motors |

With 12V / 20Ah battery (~240Wh):
- Active (no driving): ~8h
- Active (driving): ~4h
- Deep idle (Pi off): ~48h

## Switchable Power Architecture

```
12V Battery
    │
    ├── Cortex ESP32 (5V reg, always on)
    │
    ├── Relay 1 → 12V → MD25 Motor Controller
    │
    ├── Relay 2 → 5V reg → Powered USB Hub
    │              ├── Port 1: ASUS Xtion Pro
    │              ├── Port 2: USB Webcam
    │              ├── Port 3: ReSpeaker (via head)
    │              └── Port 4: Chassis ESP32
    │
    └── 5V reg → Raspberry Pi 4
```

## Cortex ESP32 – Power Controller

A dedicated ESP32 that runs always (ultra-low power, ~0.05W) and manages:

- **Watchdog**: monitors Pi heartbeat topic, reboots if unresponsive
- **Wake trigger**: listens for wake word signal from ReSpeaker (or physical button)
- **Shutdown sequence**:
  1. Publishes `/r2d2/power/state: shutting_down`
  2. Waits for Pi GPIO shutdown signal (goes low on `sudo shutdown`)
  3. Opens relay → cuts 5V to Pi
  4. Opens Relay 2 → cuts USB Hub
  5. Only Cortex ESP32 remains active
- **Boot sequence**:
  1. Receives wake signal
  2. Closes relays in sequence
  3. Monitors Pi boot completion via GPIO/serial
- **Timer-based wake**: scheduled activation (e.g. daily patrol)

## Per-Port USB Hub Control

For fine-grained USB power control without extra relays:

```bash
# Install uhubctl
sudo apt install uhubctl

# List hubs
uhubctl

# Turn off port 2 (e.g. Xtion Pro)
uhubctl -a off -p 2 -l <hub_location>

# Turn on port 2
uhubctl -a on -p 2 -l <hub_location>
```

Requires a USB Hub with Per-Port Power Switching (PPPS) support.
Check compatibility: https://github.com/mvp/uhubctl#compatible-usb-hubs

## Idle / Sleep States

| State | Active Components | Power |
|---|---|---|
| Full active | Everything | ~30W |
| Navigation idle | Pi + ESP32s + Xtion | ~12W |
| Voice-only idle | Pi + ReSpeaker | ~6W |
| Deep idle | Cortex ESP32 only | ~0.05W |

Transitions managed by Behaviour Tree → `/r2d2/power/state` topic.
