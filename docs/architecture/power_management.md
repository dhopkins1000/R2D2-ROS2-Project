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
| Chassis ESP32 | 0.1W | 0.2W | On Waveshare Hub via Pi port 4 |
| Cortex ESP32 | 0.05W | 0.05W | Always on |
| ASUS Xtion Pro | 1W | 2.5W | Pi port 2, uhubctl |
| USB Webcam | 0.5W | 0.5W | Pi port 1, uhubctl |
| ReSpeaker Mic Array | 0.5W | 1W | Pi port 3, uhubctl |
| Waveshare USB Hub | 0.1W | 0.1W | Pi port 4, uhubctl (ganged) |
| MD25 + Motors | 0W | 10–20W | Only when driving |
| SSD1306 OLED | 0.1W | 0.1W | On Chassis ESP32 |
| SerLCD + RGB Matrix | 0.2W | 0.5W | |
| **Total** | **~5.5W** | **~30W** | excl. motors |

With 12V / 20Ah battery (~240Wh):
- Active (no driving): ~8h
- Active (driving): ~4h
- Deep idle (Pi off): ~48h

## Switchable Power Architecture

Only two hardware power switches are needed. All USB devices live on the
Pi's own USB bus and are controlled via uhubctl — no external relay needed
for the hub.

```
12V Battery
    │
    ├── Cortex ESP32 (5V reg, always on)
    │
    ├── SW1: DS2413 Ch.A → N-MOSFET → 12V GND-side
    │         └── MD25 Motor Controller
    │
    └── SW2: DS2413 Ch.B → P-MOSFET → 5V VCC-side
              └── Raspberry Pi 4
                    │   hub 1-1 [2109:3431, ppps] — Pi's own USB 2.0 ports
                    ├── Port 1: USB Webcam              ← uhubctl
                    ├── Port 2: ASUS Xtion Pro          ← uhubctl
                    ├── Port 3: ReSpeaker Mic Array     ← uhubctl
                    └── Port 4: Waveshare Hub [ganged]  ← uhubctl (all-or-nothing)
                                  ├── Chassis ESP32
                                  └── (future ESP32s / peripherals)
```

All USB devices go down with the Pi (SW2 off), which is acceptable:
- Voice wake in deep idle via physical button or timer (not ReSpeaker)
- Chassis ESP32 on Waveshare Hub: no per-port switching needed, always
  runs together with Pi

## Verified uhubctl State (as of 2026-04)

```
hub 1-1 [2109:3431 USB2.0 Hub, ppps]          ← Pi's USB 2.0 ports — CONFIRMED ppps
  Port 1: Webcam (Vimicro Venus USB2.0)
  Port 2: Xtion Pro (PrimeSense)
  Port 3: ReSpeaker (SeeedStudio)
  Port 4: Waveshare Hub [1a40:0101, ganged]    ← ESP32s here, ganged is fine

hub 2 [1d6b:0003 xHCI, ppps, 4 ports]         ← Pi's USB 3.0 ports — free for future use
hub 3 [1d6b:0002 DWC OTG, ppps, 1 port]       ← Pi's OTG port
```

### uhubctl Commands

```bash
# Install
sudo apt install uhubctl

# Status
sudo uhubctl

# Xtion off (e.g. navigation idle → voice-only idle)
sudo uhubctl -a off -p 2 -l 1-1

# Webcam off
sudo uhubctl -a off -p 1 -l 1-1

# ReSpeaker off
sudo uhubctl -a off -p 3 -l 1-1

# Waveshare Hub (+ all ESP32s) off
sudo uhubctl -a off -p 4 -l 1-1
```

Note: VBUS cutoff must be verified physically (device stops charging/responding),
not just from uhubctl output — some hubs advertise ppps but don't cut VBUS.

## Power Switch Implementation: DS2413 + MOSFETs

Mechanical relays are avoided — they are noisy, draw continuous coil current,
and are slow. Instead, a single 1-Wire bus from the Cortex ESP32 drives a
**DS2413** dual-channel open-drain switch, which in turn drives MOSFETs.

### DS2413 Overview
- 1-Wire addressable dual-channel open-drain switch
- Max 20V / 20mA per channel — cannot switch load directly
- Drives MOSFET gate circuits via small NPN transistors
- Single GPIO on Cortex handles both switches
- Multiple DS2413 chips can share one 1-Wire bus if more channels needed

### Circuit: SW1 — MD25 12V GND-Side Switch

```
DS2413 Ch.A (open drain, active low)
    │
    ├── 10kΩ pull-up to 3.3V
    │
    └── Base of NPN (e.g. 2N2222) via 1kΩ
          │
          Collector → Gate of N-MOSFET (e.g. IRLZ44N)
          Emitter  → GND

IRLZ44N:
    Drain  → MD25 GND return
    Source → Battery GND
    Gate   → NPN collector (+ 10kΩ pull-down to GND)
```

When DS2413 Ch.A pulls low → NPN saturates → N-MOSFET gate pulled high →
MD25 GND path closed → MD25 powered. Logic is inverted at DS2413 level
(channel off = MOSFET on), handle in firmware.

The IRLZ44N is logic-level compatible (fully enhanced at 5V gate drive)
and rated 55V / 41A — well within margin for 12V / 20A motor load.

### Circuit: SW2 — Pi 5V VCC-Side Switch

```
DS2413 Ch.B (open drain, active low)
    │
    ├── 10kΩ pull-up to 3.3V
    │
    └── Base of NPN (e.g. 2N2222) via 1kΩ
          │
          Collector → Gate of P-MOSFET (e.g. IRF4905) via 10kΩ
          │           + Gate pulled to VCC (5V) via 47kΩ
          Emitter  → GND

IRF4905:
    Source → +5V from regulator
    Gate   → NPN drain (pulled toward GND when NPN on)
    Drain  → Pi 5V input
```

P-MOSFET switches the high side (VCC) of the 5V rail — preferred over
low-side switching for the Pi to avoid floating ground issues.
When DS2413 Ch.B pulls low → NPN on → P-MOSFET gate pulled low relative
to source → MOSFET conducts → Pi powered.

The IRF4905 is rated 55V / 74A with RDS(on) ~20mΩ — at 3A load,
voltage drop is ~60mV, power dissipation ~180mW. No heatsink needed.

### 1-Wire Wiring

```
Cortex ESP32 GPIO (1-Wire)
    │
    ├── 4.7kΩ pull-up to 3.3V
    └── DS2413
          ├── Channel A → SW1 NPN base circuit (MD25)
          └── Channel B → SW2 NPN base circuit (Pi)
```

Use the `OneWire` + `DS2413` Arduino libraries on the Cortex ESP32.

## Wake / Deep Idle

Wake from deep idle (Pi off) requires a signal path that does not depend on
the Pi or ReSpeaker. Two mechanisms are supported:

- **Physical button** wired directly to Cortex ESP32 GPIO
- **Timer-based wake** via ESP32 RTC deep sleep timer

Voice-based wake in deep idle is **not supported** — the ReSpeaker requires
the Pi to process audio. Voice wake works normally in all other states.

## Idle / Sleep States

| State | Active Components | Power | Wake Trigger |
|---|---|---|---|
| Full active | Everything | ~30W | n/a |
| Navigation idle | Pi + ESP32s + Xtion | ~12W | immediate |
| Voice-only idle | Pi + ReSpeaker | ~6W | wake word / button |
| Deep idle | Cortex ESP32 only | ~0.05W | button / timer |

Transitions managed by Behaviour Tree → `/r2d2/power/state` topic.
Cortex ESP32 executes hardware switching via DS2413.
uhubctl handles USB port switching on the Pi side.
