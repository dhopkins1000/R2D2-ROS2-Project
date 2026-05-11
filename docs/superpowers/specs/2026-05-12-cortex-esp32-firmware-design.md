# R2D2 Cortex ESP32 -- Full Firmware Design

**Date:** 2026-05-12
**Status:** Approved
**Location:** `esp32/r2d2_cortex_esp32/`

## Purpose

The Cortex is an always-on LOLIN D32 (ESP32) that manages power, battery monitoring, LED status, and a health web interface for R2D2. It runs independently of the Raspberry Pi and must function correctly in three states:

| State | Description |
|-------|-------------|
| ACTIVE | Pi running, micro-ROS connected (future) |
| STANDALONE | Pi down/booting, no micro-ROS, monitoring continues |
| DEEP_IDLE | Pi off, motors off, WiFi AP on request, HTTP health page |

Micro-ROS integration is deferred to a follow-up. This firmware is standalone-first.

## Pin Assignment

```
// UART2 -- XY-BT13L Battery Module
PIN_BAT_RX       16   // <- XY-BT13L TX (3.3V confirmed)
PIN_BAT_TX       17   // -> XY-BT13L RX

// I2C -- HT16K33 RGB 8x8 Matrix
PIN_I2C_SDA      21
PIN_I2C_SCL      22

// 1-Wire -- DS2413 Dual Power Switch
PIN_ONEWIRE       4

// Pi GPIO -- Shutdown & Wake
PIN_PI_SHUTDOWN_OUT  32  // Cortex -> Pi: pull LOW to initiate shutdown
PIN_PI_SHUTDOWN_IN   34  // Pi -> Cortex: Pi pulls LOW when shutdown complete
                         // (GPIO34 is input-only on LOLIN D32)

// Physical Buttons
PIN_WAKE_BTN     35   // Wake button (input-only, active LOW)
PIN_HEALTH_BTN   35   // Same button: long press = toggle AP mode
```

## File Structure

```
esp32/r2d2_cortex_esp32/
  platformio.ini
  .gitignore
  src/
    config.h             -- pin defs, WiFi credentials, thresholds
    main.cpp             -- setup/loop, state machine
    battery.h/.cpp       -- XY-BT13L Modbus reading + alarm handling
    power.h/.cpp         -- DS2413 1-Wire control, Pi GPIO, shutdown/wake
    leds.h/.cpp          -- HT16K33 RGB matrix animations
    health_server.h/.cpp -- WiFi AP + HTTP health page + wake button
```

## Dependencies (platformio.ini)

```ini
lib_deps =
    4-20ma/ModbusMaster@^2.0.1
    adafruit/Adafruit GFX Library@^1.11.9
    adafruit/Adafruit LED Backpack Library@^1.4.2
    paulstoffregen/OneWire@^2.3.8
```

**Decision:** Use Adafruit LED Backpack (Option A) for HT16K33 driving. The chassis ESP32 already uses Adafruit GFX, keeping library choices consistent across the project.

The `register_scan` environment from the previous battery test session is preserved for diagnostics.

## Module: config.h

All constants centralized. WiFi credentials use placeholders; `config.h` is added to `.gitignore` to avoid committing secrets.

Key thresholds:
- `BAT_SOC_LOW = 200` (raw /10 = 20.0%) -- low battery warning
- `BAT_SOC_CRITICAL = 100` (raw /10 = 10.0%) -- forced shutdown
- `BAT_VCHARGE_THRESH = 100` (raw /100 = 1.00V) -- charger detection (filters ~0.5V ADC noise)
- `BATTERY_POLL_MS = 2000`
- `PI_SHUTDOWN_WAIT_MS = 15000`

## Module: battery.h / battery.cpp

**Class:** `BatteryMonitor`

**Data struct:** `BatteryData` holds all decoded register values plus derived fields (`charger_connected`, `valid`, `last_update_ms`).

**Startup sequence (`begin()`):**
1. Read ALARM register (0x0012)
2. If alarm != 0 AND alarm != 3 (NCH): acknowledge via write, wait 200ms, log
3. Set MODE = 1 (DCHG) via `writeSingleRegister(0x0000, 1)`
4. Wait 200ms, verify DCH_RELAY (0x0002) == 1
5. Log result

**Polling (`update()`):**
- Read registers 0x0000-0x0006 (7 regs: mode, relays, Ah, Wh) in one batch
- Read registers 0x0007-0x0012 (12 regs: SOC through ALARM) in one batch
- Parse into `BatteryData`

**Scaling factors (confirmed empirically from register scan session):**
- VBAT, IBAT, VCHARGE: raw / 100
- SOC, TEMP: raw / 10
- Ah: `(AH_HIGH << 16 | AH_LOW) / 100`
- Wh: `(WH_HIGH << 16 | WH_LOW) / 100`
- Power: `(W_HIGH << 16 | W_LOW) / 1000`

**Alarm handling:**
- Code 3 (NCH): IGNORE -- normal state without charger
- Code 2 (NBE): log, do NOT block -- expected with lab PSU during development
- All others (OCP, OVP, LVP): log as WARNING

**Write operations:**
- `setMode(uint8_t mode)`: write to register 0x0000 (0=CHG, 1=DCHG, 2=UPS)
- `acknowledgeAlarm()`: write 0 to register 0x0012

## Module: power.h / power.cpp

**Class:** `PowerManager`

**DS2413 1-Wire control:**
- Channel A -> IRLZ44N MOSFET -> MD25 motor controller power
- Channel B -> IRF4905 MOSFET -> Raspberry Pi power
- Logic is inverted (open-drain LOW = MOSFET ON)

**Pi GPIO:**
- `PIN_PI_SHUTDOWN_OUT` (GPIO32): pull LOW for 500ms to signal Pi to shut down
- `PIN_PI_SHUTDOWN_IN` (GPIO34, input-only): Pi pulls LOW when shutdown complete

**Shutdown sequence:**
1. Log "shutdown initiated"
2. Pull `PIN_PI_SHUTDOWN_OUT` LOW for 500ms, then HIGH
3. Wait for `PIN_PI_SHUTDOWN_IN` LOW (Pi done) OR timeout after 15s
4. DS2413: MD25 OFF, Pi OFF
5. State -> DEEP_IDLE

**Wake sequence:**
1. DS2413: Pi ON
2. Wait 2s
3. State -> STANDALONE (MD25 ON deferred until explicit drive command)

**Safety constraints:**
- Never turn Pi power OFF without confirming shutdown complete (or timeout)
- Never turn MD25 ON without Pi being powered first

## Module: leds.h / leds.cpp

**Class:** `LEDMatrix`
**Hardware:** HT16K33 at I2C address 0x70, driven via Adafruit LED Backpack
**Interface:** I2C on GPIO21/22 (Wire)

**Patterns (non-blocking, millis-based):**

| Pattern | Color | Animation | When |
|---------|-------|-----------|------|
| BOOT | White | Wipe left->right | Startup |
| ACTIVE | Blue | Slow pulse | Pi running |
| STANDALONE | Yellow | Slow pulse | Pi down |
| DEEP_IDLE | Orange | Single pixel drift | Everything off |
| ERROR | Red | Fast blink | Error state |
| CHARGING | Violet | Slow sweep | Charger detected |
| LOW_BATTERY | Violet | Fast blink | SOC < 20% |
| HEALTH_AP | Cyan | Slow pulse | AP mode active |
| SHUTDOWN | Red | Fade out | Shutting down |
| NAVIGATING | Green | Rotating | Moving (future) |
| LISTENING | Cyan | Fast pulse | Voice input (future) |
| SPEAKING | Yellow | Wave | Voice output (future) |

Implementation uses `Adafruit_BicolorMatrix` (HT16K33 drives bicolor red/green LEDs, not true RGB). Available hardware colors: RED, GREEN, YELLOW (red+green). Pattern color mapping:

| Spec Color | Hardware Color |
|------------|---------------|
| White | YELLOW |
| Blue | GREEN |
| Yellow | YELLOW |
| Orange | YELLOW |
| Red | RED |
| Violet | RED |
| Cyan | GREEN |
| Green | GREEN |

All animations driven by `update()` called every loop iteration, non-blocking via millis().

## Module: health_server.h / health_server.cpp

**Class:** `HealthServer`

**WiFi behavior:**
- On `begin()`: attempt STA connection to configured SSID, timeout after 10s, continue offline
- `enableAP()`: disconnect STA, start AP "R2D2-Status" with password, start HTTP server
- HTTP server runs in both STA and AP modes
- AP accessible at 192.168.4.1

**HTTP routes:**
- `GET /` -- HTML health page (dark theme, mobile-friendly, auto-refresh 5s)
- `GET /status` -- JSON status object
- `POST /wake` -- trigger wake sequence
- `POST /sleep` -- trigger shutdown sequence

**Health page features:**
- Shows: VBAT, SOC%, IBAT, TEMP, Mode, Alarm, Pi status, Motor status
- Wake/Sleep buttons with JS `confirm()` dialog
- Current WiFi mode and IP address
- Inline CSS, no external dependencies

**JSON `/status` response format:**
```json
{
  "vbat": 13.13, "soc": 49.5, "ibat": 0.16, "temp": 26.2,
  "mode": "DCHG", "alarm": 3, "alarm_name": "NCH",
  "charger": false, "pi_on": false, "motors_on": false,
  "uptime_s": 3600, "wifi_mode": "AP", "ip": "192.168.4.1"
}
```

## Module: main.cpp -- State Machine

**States:**
```
STATE_BOOT       -> initial setup
STATE_ACTIVE     -> Pi running, micro-ROS connected (future)
STATE_STANDALONE -> Pi down, monitoring continues
STATE_DEEP_IDLE  -> Pi off, everything off
```

**setup():**
1. `Serial.begin(115200)`
2. `leds.begin()` -> BOOT pattern
3. `power.begin()` -> DS2413 init
4. `battery.begin()` -> XY-BT13L init + startup sequence
5. `healthServer.begin(&battery, &power)`
6. Log all init results

**loop() (all non-blocking):**
1. `battery.update()` every `BATTERY_POLL_MS`
2. `leds.update()` every loop
3. `healthServer.update()` every loop
4. Wake button (GPIO35):
   - Short press (<1s) + DEEP_IDLE -> `executeWake()`
   - Long press (>3s) -> toggle AP mode
5. `healthServer.wakeRequested()` -> `executeWake()`
6. Battery alerts:
   - SOC < 20%: `setPattern(LOW_BATTERY)`
   - SOC < 10%: `executeShutdown()`
   - Charger connected: `setMode(UPS)`, `setPattern(CHARGING)`
   - Charger disconnected: `setMode(DCHG)`
7. Serial status print every 10s

## Constraints

1. **No blocking calls in loop()** -- all timing via millis()
2. **DS2413 safety** -- never cut Pi power without shutdown confirmation or timeout
3. **NCH (alarm 3) is never an alert** -- normal without charger
4. **NBE (alarm 2) is dev-normal** -- log only, no blocking
5. **config.h in .gitignore** -- WiFi credentials never committed
6. **Wake/Sleep buttons require JS confirm()** -- prevent accidental triggers

## Expected Boot Output

```
[CORTEX] Booting...
[BAT] XY-BT13L connected. VBAT=13.13V SOC=49.5% ALARM=NCH(normal)
[BAT] Mode set to DCHG. DCH_RELAY=ON confirmed.
[POWER] DS2413 initialized. MD25=OFF Pi=OFF
[WIFI] Connecting to <SSID>...
[WIFI] Connected. IP=192.168.x.x
[HTTP] Health server running at http://192.168.x.x
[CORTEX] Ready. State=STANDALONE
```
