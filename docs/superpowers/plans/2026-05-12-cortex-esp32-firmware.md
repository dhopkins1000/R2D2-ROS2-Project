# R2D2 Cortex ESP32 Full Firmware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete standalone firmware for the Cortex ESP32 -- battery monitoring, power management (DS2413), LED status matrix (HT16K33), WiFi health server, and state machine.

**Architecture:** Module-per-concern with a central state machine in main.cpp. Each module (battery, power, leds, health_server) is a class with `begin()` + `update()` pattern. All loop operations are non-blocking (millis-based). The existing `register_scan.cpp` diagnostic tool is preserved as a separate PlatformIO environment.

**Tech Stack:** PlatformIO + Arduino framework on ESP32 (LOLIN D32). Libraries: ModbusMaster (Modbus RTU), Adafruit LED Backpack + GFX (HT16K33), OneWire (DS2413), ESP32 WiFi + WebServer (built-in).

**Spec:** `docs/superpowers/specs/2026-05-12-cortex-esp32-firmware-design.md`

---

## File Map

| File | Responsibility | Task |
|------|---------------|------|
| `platformio.ini` | Build config, environments, lib_deps | Task 1 |
| `.gitignore` | Ignore .pio/ and config.h | Task 1 |
| `src/config.h` | All pin defs, WiFi creds, thresholds | Task 1 |
| `src/battery.h` | BatteryData struct, BatteryMonitor class declaration | Task 2 |
| `src/battery.cpp` | Modbus read/write, register parsing, alarm handling | Task 2 |
| `src/power.h` | PowerManager class declaration | Task 3 |
| `src/power.cpp` | DS2413 1-Wire control, Pi GPIO, shutdown/wake sequences | Task 3 |
| `src/leds.h` | LEDPattern enum, LEDMatrix class declaration | Task 4 |
| `src/leds.cpp` | HT16K33 animations via Adafruit BicolorMatrix | Task 4 |
| `src/health_server.h` | HealthServer class declaration | Task 5 |
| `src/health_server.cpp` | WiFi AP/STA, HTTP routes, HTML health page | Task 5 |
| `src/main.cpp` | State machine, setup/loop, button handling | Task 6 |
| `src/register_scan.cpp` | (Existing) Diagnostic register scanner -- preserved | -- |

---

### Task 1: Project Scaffolding -- platformio.ini, config.h, .gitignore

**Files:**
- Modify: `esp32/r2d2_cortex_esp32/platformio.ini`
- Modify: `esp32/r2d2_cortex_esp32/.gitignore`
- Create: `esp32/r2d2_cortex_esp32/src/config.h`

This task replaces the existing battery-test-only platformio.ini with the full firmware config, adds config.h to .gitignore (WiFi credentials), and creates the central config header.

- [ ] **Step 1: Update platformio.ini**

Replace the current contents of `esp32/r2d2_cortex_esp32/platformio.ini` with:

```ini
; ============================================================
; R2D2 Cortex ESP32 -- PlatformIO Config
; Board: LOLIN D32 (ESP32)
; Role: Always-on power/battery/status controller
; ============================================================

[env:lolin_d32]
platform = espressif32
board = lolin_d32
framework = arduino
monitor_speed = 115200
build_src_filter =
    +<config.h>
    +<main.cpp>
    +<battery.cpp>
    +<power.cpp>
    +<leds.cpp>
    +<health_server.cpp>
lib_deps =
    4-20ma/ModbusMaster@^2.0.1
    adafruit/Adafruit GFX Library@^1.11.9
    adafruit/Adafruit LED Backpack Library@^1.4.2
    paulstoffregen/OneWire@^2.3.8

[env:register_scan]
platform = espressif32
board = lolin_d32
framework = arduino
monitor_speed = 115200
lib_deps = 4-20ma/ModbusMaster@^2.0.1
build_src_filter = +<register_scan.cpp>
```

- [ ] **Step 2: Update .gitignore**

Replace the contents of `esp32/r2d2_cortex_esp32/.gitignore` with:

```
.pio/
src/config.h
```

- [ ] **Step 3: Create config.h**

Create `esp32/r2d2_cortex_esp32/src/config.h`:

```cpp
#pragma once

// ============================================================
// R2D2 Cortex ESP32 -- Configuration
// All pins, credentials, and thresholds defined here.
// This file is in .gitignore -- do not commit with real creds.
// ============================================================

#include <Arduino.h>
#include <IPAddress.h>

// --- UART2: XY-BT13L Battery Module ---
#define PIN_BAT_RX          16   // <- XY-BT13L TX (3.3V confirmed)
#define PIN_BAT_TX          17   // -> XY-BT13L RX
#define MODBUS_BAUD         115200
#define MODBUS_SLAVE_ADDR   1

// --- I2C: HT16K33 RGB 8x8 Matrix ---
#define PIN_I2C_SDA         21
#define PIN_I2C_SCL         22
#define HT16K33_ADDR        0x70

// --- 1-Wire: DS2413 Dual Power Switch ---
#define PIN_ONEWIRE         4

// --- Pi GPIO: Shutdown & Wake ---
#define PIN_PI_SHUTDOWN_OUT 32   // Cortex -> Pi: pull LOW to initiate shutdown
#define PIN_PI_SHUTDOWN_IN  34   // Pi -> Cortex: LOW = shutdown complete (input-only)

// --- Physical Button ---
#define PIN_WAKE_BTN        35   // Wake/Health button (input-only, active LOW)

// --- WiFi: Station mode (home network) ---
#define WIFI_SSID           "YOUR_SSID"
#define WIFI_PASSWORD       "YOUR_PASSWORD"

// --- WiFi: AP mode (health access point) ---
#define AP_SSID             "R2D2-Status"
#define AP_PASSWORD         "r2d2health"
#define AP_IP               IPAddress(192, 168, 4, 1)

// --- HTTP Server ---
#define HTTP_PORT           80

// --- Battery thresholds (raw register values) ---
#define BAT_SOC_LOW         200   // raw /10 = 20.0% -> low battery warning
#define BAT_SOC_CRITICAL    100   // raw /10 = 10.0% -> forced shutdown
#define BAT_VCHARGE_THRESH  100   // raw /100 = 1.00V -> charger connected

// --- Timing ---
#define BATTERY_POLL_MS     2000
#define STATUS_PRINT_MS     10000
#define WATCHDOG_TIMEOUT_MS 60000
#define PI_SHUTDOWN_WAIT_MS 15000  // max wait for Pi to finish shutdown
#define BUTTON_LONG_PRESS_MS 3000  // long press threshold for AP toggle
```

- [ ] **Step 4: Verify build compiles (scaffolding only)**

We cannot build yet (main.cpp still references old code), but verify the config is syntactically valid by creating a minimal temporary main to test:

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e register_scan 2>&1 | tail -5`

Expected: register_scan env still builds cleanly (it does not depend on config.h).

- [ ] **Step 5: Commit**

```bash
cd esp32/r2d2_cortex_esp32
git add platformio.ini .gitignore
git commit -m "chore(cortex): update platformio.ini for full firmware, add config.h to gitignore"
```

Note: config.h is NOT committed (it's in .gitignore). Document in the commit message that config.h must be created locally with WiFi credentials.

---

### Task 2: Battery Monitor Module -- battery.h / battery.cpp

**Files:**
- Create: `esp32/r2d2_cortex_esp32/src/battery.h`
- Create: `esp32/r2d2_cortex_esp32/src/battery.cpp`

This module evolves the proven battery test sketch into a proper class. All register addresses, scaling factors, and alarm codes are empirically confirmed from the register scan session.

- [ ] **Step 1: Create battery.h**

Create `esp32/r2d2_cortex_esp32/src/battery.h`:

```cpp
#pragma once

#include <Arduino.h>
#include <ModbusMaster.h>
#include "config.h"

struct BatteryData {
    float vbat;          // V  (raw / 100)
    float ibat;          // A  (raw / 100)
    float vcharge;       // V  (raw / 100, 0 if below threshold)
    float soc;           // %  (raw / 10)
    float temp;          // C  (raw / 10)
    float ah_remain;     // Ah ((AH_HIGH<<16 | AH_LOW) / 100)
    float wh_remain;     // Wh ((WH_HIGH<<16 | WH_LOW) / 100)
    float power_w;       // W  ((W_HIGH<<16 | W_LOW) / 1000)
    uint16_t mode;       // 0=CHG, 1=DCHG, 2=UPS
    uint16_t alarm;      // alarm code
    bool charger_connected;  // vcharge raw > BAT_VCHARGE_THRESH
    bool relay_dch;      // DCH_RELAY status
    bool valid;          // last read succeeded
    uint32_t last_update_ms;
};

class BatteryMonitor {
public:
    void begin();
    bool update();                // call every BATTERY_POLL_MS, returns true if new data
    const BatteryData& getData() const { return _data; }
    bool setMode(uint8_t mode);   // 0=CHG, 1=DCHG, 2=UPS
    bool acknowledgeAlarm();      // write 0 to ALARM register
    bool isAlarmBlocking() const; // true if alarm blocks relay (not NCH, not NBE)

    static const char* alarmName(uint16_t code);
    static const char* modeName(uint16_t mode);

private:
    ModbusMaster _node;
    BatteryData _data = {};
    uint32_t _lastPollMs = 0;

    bool readAllRegisters();
};
```

- [ ] **Step 2: Create battery.cpp**

Create `esp32/r2d2_cortex_esp32/src/battery.cpp`:

```cpp
#include "battery.h"

// --- Modbus register addresses ---
static constexpr uint16_t REG_MODE       = 0x0000;
static constexpr uint16_t REG_CH_RELAY   = 0x0001;
static constexpr uint16_t REG_DCH_RELAY  = 0x0002;
static constexpr uint16_t REG_AH_LOW     = 0x0003;
static constexpr uint16_t REG_AH_HIGH    = 0x0004;
static constexpr uint16_t REG_WH_LOW     = 0x0005;
static constexpr uint16_t REG_WH_HIGH    = 0x0006;
static constexpr uint16_t REG_PER        = 0x0007;
static constexpr uint16_t REG_VCHARGE    = 0x0008;
static constexpr uint16_t REG_VBAT       = 0x0009;
static constexpr uint16_t REG_IBAT       = 0x000A;
static constexpr uint16_t REG_W_LOW      = 0x000B;
static constexpr uint16_t REG_W_HIGH     = 0x000C;
static constexpr uint16_t REG_IN_TEMP    = 0x0010;
static constexpr uint16_t REG_ALARM      = 0x0012;

// Alarm codes
static constexpr uint16_t ALARM_OK   = 0;
static constexpr uint16_t ALARM_OCP  = 1;
static constexpr uint16_t ALARM_NBE  = 2;
static constexpr uint16_t ALARM_NCH  = 3;
static constexpr uint16_t ALARM_OVP  = 10;
static constexpr uint16_t ALARM_LVP  = 11;

const char* BatteryMonitor::alarmName(uint16_t code) {
    switch (code) {
        case ALARM_OK:  return "OK";
        case ALARM_OCP: return "OCP";
        case ALARM_NBE: return "NBE";
        case ALARM_NCH: return "NCH";
        case ALARM_OVP: return "OVP";
        case ALARM_LVP: return "LVP";
        default:        return "UNKNOWN";
    }
}

const char* BatteryMonitor::modeName(uint16_t mode) {
    switch (mode) {
        case 0:  return "CHG";
        case 1:  return "DCHG";
        case 2:  return "UPS";
        default: return "???";
    }
}

bool BatteryMonitor::isAlarmBlocking() const {
    return _data.alarm != ALARM_OK
        && _data.alarm != ALARM_NCH
        && _data.alarm != ALARM_NBE;
}

void BatteryMonitor::begin() {
    Serial2.begin(MODBUS_BAUD, SERIAL_8N1, PIN_BAT_RX, PIN_BAT_TX);
    _node.begin(MODBUS_SLAVE_ADDR, Serial2);

    Serial.println("[BAT] Initializing XY-BT13L...");

    // Step 1: Read current alarm
    delay(100);
    uint8_t result = _node.readHoldingRegisters(REG_ALARM, 1);
    if (result == _node.ku8MBSuccess) {
        uint16_t alarm = _node.getResponseBuffer(0);
        Serial.printf("[BAT] Current ALARM=%u (%s)\n", alarm, alarmName(alarm));

        // Step 2: Acknowledge blocking alarms (not NCH, not NBE)
        if (alarm != ALARM_OK && alarm != ALARM_NCH && alarm != ALARM_NBE) {
            Serial.printf("[BAT] Acknowledging alarm %s...\n", alarmName(alarm));
            _node.writeSingleRegister(REG_ALARM, 0);
            delay(200);
        }
    } else {
        Serial.printf("[BAT] WARNING: Could not read ALARM register (result=0x%02X)\n", result);
    }

    // Step 3: Set MODE = DCHG (1)
    delay(100);
    result = _node.writeSingleRegister(REG_MODE, 1);
    if (result == _node.ku8MBSuccess) {
        Serial.println("[BAT] Mode set to DCHG.");
    } else {
        Serial.printf("[BAT] WARNING: Could not set MODE (result=0x%02X)\n", result);
    }

    // Step 4: Verify DCH_RELAY is ON
    delay(200);
    result = _node.readHoldingRegisters(REG_DCH_RELAY, 1);
    if (result == _node.ku8MBSuccess) {
        uint16_t relay = _node.getResponseBuffer(0);
        Serial.printf("[BAT] DCH_RELAY=%u %s\n", relay, relay ? "confirmed." : "WARNING: not active!");
    }

    // Step 5: Do initial full read
    if (readAllRegisters()) {
        Serial.printf("[BAT] XY-BT13L connected. VBAT=%.2fV SOC=%.1f%% ALARM=%s(%s)\n",
                      _data.vbat, _data.soc, alarmName(_data.alarm),
                      (_data.alarm == ALARM_NCH) ? "normal" : "active");
    } else {
        Serial.println("[BAT] WARNING: Initial register read failed.");
    }
}

bool BatteryMonitor::update() {
    uint32_t now = millis();
    if (now - _lastPollMs < BATTERY_POLL_MS) return false;
    _lastPollMs = now;

    return readAllRegisters();
}

bool BatteryMonitor::readAllRegisters() {
    _data.valid = false;

    // Batch 1: registers 0x0000..0x0006 (mode, relays, Ah, Wh)
    // Important: save values before issuing batch 2 -- ModbusMaster
    // reuses a single response buffer that gets overwritten.
    uint8_t r1 = _node.readHoldingRegisters(REG_MODE, 7);
    if (r1 != _node.ku8MBSuccess) {
        Serial.printf("[BAT] Batch1 read failed (0x%02X)\n", r1);
        return false;
    }

    uint16_t rawMode     = _node.getResponseBuffer(0);  // 0x0000
    uint16_t rawChRelay  = _node.getResponseBuffer(1);  // 0x0001
    uint16_t rawDchRelay = _node.getResponseBuffer(2);  // 0x0002
    uint16_t rawAhLow    = _node.getResponseBuffer(3);  // 0x0003
    uint16_t rawAhHigh   = _node.getResponseBuffer(4);  // 0x0004
    uint16_t rawWhLow    = _node.getResponseBuffer(5);  // 0x0005
    uint16_t rawWhHigh   = _node.getResponseBuffer(6);  // 0x0006

    delay(10);

    // Batch 2
    r2 = _node.readHoldingRegisters(REG_PER, 12);
    if (r2 != _node.ku8MBSuccess) {
        Serial.printf("[BAT] Batch2 read failed (0x%02X)\n", r2);
        return false;
    }

    uint16_t rawSOC     = _node.getResponseBuffer(0);   // 0x0007
    uint16_t rawVcharge = _node.getResponseBuffer(1);   // 0x0008
    uint16_t rawVbat    = _node.getResponseBuffer(2);   // 0x0009
    uint16_t rawIbat    = _node.getResponseBuffer(3);   // 0x000A
    uint16_t rawWLow    = _node.getResponseBuffer(4);   // 0x000B
    uint16_t rawWHigh   = _node.getResponseBuffer(5);   // 0x000C
    uint16_t rawTemp    = _node.getResponseBuffer(9);   // 0x0010
    uint16_t rawAlarm   = _node.getResponseBuffer(11);  // 0x0012

    // Convert and store
    _data.mode             = rawMode;
    _data.relay_dch        = (rawDchRelay != 0);
    _data.alarm            = rawAlarm;
    _data.vbat             = rawVbat / 100.0f;
    _data.ibat             = rawIbat / 100.0f;
    _data.soc              = rawSOC / 10.0f;
    _data.temp             = rawTemp / 10.0f;
    _data.charger_connected = (rawVcharge > BAT_VCHARGE_THRESH);
    _data.vcharge          = _data.charger_connected ? (rawVcharge / 100.0f) : 0.0f;
    _data.ah_remain        = ((uint32_t)rawAhHigh << 16 | rawAhLow) / 100.0f;
    _data.wh_remain        = ((uint32_t)rawWhHigh << 16 | rawWhLow) / 100.0f;
    _data.power_w          = ((uint32_t)rawWHigh << 16 | rawWLow) / 1000.0f;
    _data.valid            = true;
    _data.last_update_ms   = millis();

    return true;
}

bool BatteryMonitor::setMode(uint8_t mode) {
    uint8_t result = _node.writeSingleRegister(REG_MODE, mode);
    if (result == _node.ku8MBSuccess) {
        Serial.printf("[BAT] Mode set to %s\n", modeName(mode));
        return true;
    }
    Serial.printf("[BAT] Failed to set mode (result=0x%02X)\n", result);
    return false;
}

bool BatteryMonitor::acknowledgeAlarm() {
    uint8_t result = _node.writeSingleRegister(REG_ALARM, 0);
    if (result == _node.ku8MBSuccess) {
        Serial.println("[BAT] Alarm acknowledged.");
        return true;
    }
    Serial.printf("[BAT] Failed to acknowledge alarm (result=0x%02X)\n", result);
    return false;
}
```

- [ ] **Step 3: Build battery module in isolation**

Temporarily create a minimal main.cpp stub to verify battery.h/cpp compile:

Create a temporary `esp32/r2d2_cortex_esp32/src/main.cpp`:

```cpp
#include <Arduino.h>
#include "battery.h"

BatteryMonitor battery;

void setup() {
    Serial.begin(115200);
    battery.begin();
}

void loop() {
    battery.update();
    delay(10);
}
```

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 2>&1 | tail -10`

Expected: BUILD SUCCESS. Fix any compile errors before proceeding.

- [ ] **Step 4: Flash and verify battery communication**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 --target upload`

Then monitor: capture ~10s of serial output with:
```bash
python3 -c "
import serial, time
ser = serial.Serial('/dev/cu.usbserial-5AA70048951', 115200, timeout=1)
end = time.time() + 10
while time.time() < end:
    line = ser.readline().decode('utf-8', errors='replace').rstrip()
    if line: print(line)
ser.close()
"
```

Expected output should include:
```
[BAT] Initializing XY-BT13L...
[BAT] Current ALARM=2 (NBE)
[BAT] Mode set to DCHG.
[BAT] DCH_RELAY=1 confirmed.
[BAT] XY-BT13L connected. VBAT=13.13V SOC=49.5% ALARM=NBE(active)
```

- [ ] **Step 5: Commit**

```bash
git add src/battery.h src/battery.cpp
git commit -m "feat(cortex): add BatteryMonitor module for XY-BT13L Modbus RTU"
```

---

### Task 3: Power Manager Module -- power.h / power.cpp

**Files:**
- Create: `esp32/r2d2_cortex_esp32/src/power.h`
- Create: `esp32/r2d2_cortex_esp32/src/power.cpp`

DS2413 is a 1-Wire dual-channel open-drain switch. Each channel controls a MOSFET gate. Logic is inverted: writing LOW to DS2413 output turns the MOSFET ON.

- [ ] **Step 1: Create power.h**

Create `esp32/r2d2_cortex_esp32/src/power.h`:

```cpp
#pragma once

#include <Arduino.h>
#include <OneWire.h>
#include "config.h"

class PowerManager {
public:
    void begin();

    // DS2413 channel control
    void setMD25Power(bool on);    // Ch.A -> IRLZ44N -> MD25
    void setPiPower(bool on);      // Ch.B -> IRF4905 -> Pi
    bool getMD25Power() const { return _md25On; }
    bool getPiPower() const { return _piOn; }

    // Pi GPIO shutdown/wake
    void initiatePiShutdown();     // signal Pi to shut down
    bool isPiShutdownComplete();   // true if Pi confirms shutdown (GPIO34 LOW)

    // High-level sequences (non-blocking, call from loop)
    void startShutdownSequence();
    void startWakeSequence();
    bool isSequenceRunning() const { return _seqState != SEQ_IDLE; }
    void updateSequence();         // call every loop() to advance sequence

private:
    OneWire _ow{PIN_ONEWIRE};
    uint8_t _ds2413Addr[8] = {};
    bool _ds2413Found = false;
    bool _md25On = false;
    bool _piOn = false;

    // Sequence state machine
    enum SeqState {
        SEQ_IDLE,
        SEQ_SHUTDOWN_SIGNAL_SENT,
        SEQ_SHUTDOWN_WAIT_PI,
        SEQ_SHUTDOWN_POWER_OFF,
        SEQ_WAKE_PI_ON,
        SEQ_WAKE_DONE,
    };
    SeqState _seqState = SEQ_IDLE;
    uint32_t _seqStartMs = 0;

    bool ds2413Write(bool chA, bool chB);
    void applyPower();
};
```

- [ ] **Step 2: Create power.cpp**

Create `esp32/r2d2_cortex_esp32/src/power.cpp`:

```cpp
#include "power.h"

// DS2413 commands
static constexpr uint8_t DS2413_ACCESS_WRITE = 0x5A;
static constexpr uint8_t DS2413_ACK_BYTE     = 0xAA;

void PowerManager::begin() {
    // Pi GPIO pins
    pinMode(PIN_PI_SHUTDOWN_OUT, OUTPUT);
    digitalWrite(PIN_PI_SHUTDOWN_OUT, HIGH);  // idle HIGH
    pinMode(PIN_PI_SHUTDOWN_IN, INPUT);       // GPIO34 is input-only

    // Discover DS2413 on 1-Wire bus
    _ow.reset_search();
    if (_ow.search(_ds2413Addr)) {
        if (_ds2413Addr[0] == 0x3A) {  // DS2413 family code
            _ds2413Found = true;
            Serial.printf("[POWER] DS2413 found: %02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X\n",
                          _ds2413Addr[0], _ds2413Addr[1], _ds2413Addr[2], _ds2413Addr[3],
                          _ds2413Addr[4], _ds2413Addr[5], _ds2413Addr[6], _ds2413Addr[7]);
        } else {
            Serial.printf("[POWER] WARNING: 1-Wire device found but not DS2413 (family=0x%02X)\n",
                          _ds2413Addr[0]);
        }
    } else {
        Serial.println("[POWER] WARNING: No DS2413 found on 1-Wire bus. Power control disabled.");
    }

    // Start with everything OFF
    _md25On = false;
    _piOn = false;
    applyPower();

    Serial.printf("[POWER] Initialized. MD25=%s Pi=%s\n",
                  _md25On ? "ON" : "OFF", _piOn ? "ON" : "OFF");
}

bool PowerManager::ds2413Write(bool chA, bool chB) {
    if (!_ds2413Found) return false;

    // DS2413 PIO Access Write:
    // Bit 0 = PIOA state, Bit 1 = PIOB state
    // LOW = conducting (MOSFET ON due to inverted logic)
    // We invert: true=ON means we write LOW (0)
    uint8_t state = 0x03;  // both OFF (high) by default
    if (chA) state &= ~0x01;  // PIOA LOW = MD25 ON
    if (chB) state &= ~0x02;  // PIOB LOW = Pi ON

    uint8_t data = state | ((~state & 0x03) << 2);  // complement in bits 2-3

    _ow.reset();
    _ow.select(_ds2413Addr);
    _ow.write(DS2413_ACCESS_WRITE);
    _ow.write(data);

    uint8_t ack = _ow.read();
    if (ack == DS2413_ACK_BYTE) {
        _ow.reset();
        return true;
    }

    Serial.printf("[POWER] DS2413 write failed (ack=0x%02X)\n", ack);
    _ow.reset();
    return false;
}

void PowerManager::applyPower() {
    ds2413Write(_md25On, _piOn);
}

void PowerManager::setMD25Power(bool on) {
    if (on && !_piOn) {
        Serial.println("[POWER] SAFETY: Cannot enable MD25 without Pi powered. Ignoring.");
        return;
    }
    _md25On = on;
    applyPower();
    Serial.printf("[POWER] MD25=%s\n", on ? "ON" : "OFF");
}

void PowerManager::setPiPower(bool on) {
    if (!on && _md25On) {
        Serial.println("[POWER] Turning MD25 OFF before Pi power off.");
        _md25On = false;
    }
    _piOn = on;
    applyPower();
    Serial.printf("[POWER] Pi=%s\n", on ? "ON" : "OFF");
}

void PowerManager::initiatePiShutdown() {
    Serial.println("[POWER] Sending shutdown signal to Pi...");
    digitalWrite(PIN_PI_SHUTDOWN_OUT, LOW);
    // The sequence state machine will release it after 500ms
}

bool PowerManager::isPiShutdownComplete() {
    return digitalRead(PIN_PI_SHUTDOWN_IN) == LOW;
}

void PowerManager::startShutdownSequence() {
    if (_seqState != SEQ_IDLE) {
        Serial.println("[POWER] Sequence already running, ignoring shutdown request.");
        return;
    }
    Serial.println("[POWER] === Shutdown sequence initiated ===");
    initiatePiShutdown();
    _seqState = SEQ_SHUTDOWN_SIGNAL_SENT;
    _seqStartMs = millis();
}

void PowerManager::startWakeSequence() {
    if (_seqState != SEQ_IDLE) {
        Serial.println("[POWER] Sequence already running, ignoring wake request.");
        return;
    }
    Serial.println("[POWER] === Wake sequence initiated ===");
    setPiPower(true);
    _seqState = SEQ_WAKE_PI_ON;
    _seqStartMs = millis();
}

void PowerManager::updateSequence() {
    uint32_t elapsed = millis() - _seqStartMs;

    switch (_seqState) {
        case SEQ_IDLE:
            break;

        case SEQ_SHUTDOWN_SIGNAL_SENT:
            // Release shutdown pin after 500ms
            if (elapsed >= 500) {
                digitalWrite(PIN_PI_SHUTDOWN_OUT, HIGH);
                Serial.println("[POWER] Shutdown signal released. Waiting for Pi...");
                _seqState = SEQ_SHUTDOWN_WAIT_PI;
                _seqStartMs = millis();
            }
            break;

        case SEQ_SHUTDOWN_WAIT_PI:
            if (isPiShutdownComplete()) {
                Serial.println("[POWER] Pi shutdown confirmed.");
                _seqState = SEQ_SHUTDOWN_POWER_OFF;
            } else if (elapsed >= PI_SHUTDOWN_WAIT_MS) {
                Serial.println("[POWER] Pi shutdown timeout. Cutting power anyway.");
                _seqState = SEQ_SHUTDOWN_POWER_OFF;
            }
            break;

        case SEQ_SHUTDOWN_POWER_OFF:
            setMD25Power(false);
            setPiPower(false);
            Serial.println("[POWER] === Shutdown complete. DEEP_IDLE ===");
            _seqState = SEQ_IDLE;
            break;

        case SEQ_WAKE_PI_ON:
            // Wait 2s after Pi power on
            if (elapsed >= 2000) {
                Serial.println("[POWER] === Wake complete. STANDALONE ===");
                _seqState = SEQ_WAKE_DONE;
            }
            break;

        case SEQ_WAKE_DONE:
            _seqState = SEQ_IDLE;
            break;
    }
}
```

- [ ] **Step 3: Update temporary main.cpp to include power**

Update the temporary `src/main.cpp`:

```cpp
#include <Arduino.h>
#include "battery.h"
#include "power.h"

BatteryMonitor battery;
PowerManager power;

void setup() {
    Serial.begin(115200);
    Serial.println("[CORTEX] Booting...");
    power.begin();
    battery.begin();
}

void loop() {
    battery.update();
    power.updateSequence();
    delay(10);
}
```

- [ ] **Step 4: Build and verify**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 2>&1 | tail -10`

Expected: BUILD SUCCESS.

- [ ] **Step 5: Flash and verify serial output**

Run: `pio run -e lolin_d32 --target upload`

Monitor serial output. Expected:
```
[CORTEX] Booting...
[POWER] WARNING: No DS2413 found on 1-Wire bus. Power control disabled.
[POWER] Initialized. MD25=OFF Pi=OFF
[BAT] Initializing XY-BT13L...
```

(DS2413 warning is expected if the 1-Wire device is not connected during bench testing.)

- [ ] **Step 6: Commit**

```bash
git add src/power.h src/power.cpp src/main.cpp
git commit -m "feat(cortex): add PowerManager module for DS2413 + Pi GPIO control"
```

---

### Task 4: LED Matrix Module -- leds.h / leds.cpp

**Files:**
- Create: `esp32/r2d2_cortex_esp32/src/leds.h`
- Create: `esp32/r2d2_cortex_esp32/src/leds.cpp`

Uses Adafruit_BicolorMatrix (HT16K33). Hardware colors: LED_RED, LED_GREEN, LED_YELLOW. All patterns are non-blocking (millis-based), updated via `update()` in loop.

- [ ] **Step 1: Create leds.h**

Create `esp32/r2d2_cortex_esp32/src/leds.h`:

```cpp
#pragma once

#include <Arduino.h>
#include "config.h"

enum LEDPattern {
    PAT_OFF,
    PAT_BOOT,        // Yellow wipe left->right
    PAT_ACTIVE,      // Green slow pulse
    PAT_STANDALONE,  // Yellow slow pulse
    PAT_DEEP_IDLE,   // Yellow single pixel drift
    PAT_ERROR,       // Red fast blink
    PAT_CHARGING,    // Red slow sweep
    PAT_LOW_BATTERY, // Red fast blink
    PAT_HEALTH_AP,   // Green slow pulse
    PAT_SHUTDOWN,    // Red fade out
    PAT_NAVIGATING,  // Green rotating
    PAT_LISTENING,   // Green fast pulse
    PAT_SPEAKING,    // Yellow wave
};

class LEDMatrix {
public:
    void begin();
    void setPattern(LEDPattern pattern);
    LEDPattern getPattern() const { return _pattern; }
    void update();               // call every loop()
    void setBrightness(uint8_t level);  // 0-15

private:
    LEDPattern _pattern = PAT_OFF;
    LEDPattern _prevPattern = PAT_OFF;
    uint32_t _lastUpdateMs = 0;
    uint32_t _patternStartMs = 0;
    uint8_t _frame = 0;
    bool _initialized = false;

    void clear();
    void show();
    void fillAll(uint8_t color);
    void drawColumn(uint8_t col, uint8_t color);
    void drawPixel(uint8_t x, uint8_t y, uint8_t color);

    // Pattern renderers
    void renderBoot();
    void renderPulse(uint8_t color, uint16_t periodMs);
    void renderPixelDrift(uint8_t color);
    void renderBlink(uint8_t color, uint16_t periodMs);
    void renderSweep(uint8_t color);
    void renderFadeOut(uint8_t color);
    void renderRotating(uint8_t color);
    void renderWave(uint8_t color);
};
```

- [ ] **Step 2: Create leds.cpp**

Create `esp32/r2d2_cortex_esp32/src/leds.cpp`:

```cpp
#include "leds.h"
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_LEDBackpack.h>

static Adafruit_BicolorMatrix matrix = Adafruit_BicolorMatrix();

void LEDMatrix::begin() {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

    if (matrix.begin(HT16K33_ADDR)) {
        _initialized = true;
        matrix.setBrightness(5);
        matrix.clear();
        matrix.writeDisplay();
        Serial.println("[LED] HT16K33 initialized at 0x70.");
    } else {
        Serial.println("[LED] WARNING: HT16K33 not found. LED display disabled.");
    }
}

void LEDMatrix::setPattern(LEDPattern pattern) {
    if (pattern == _pattern) return;
    _prevPattern = _pattern;
    _pattern = pattern;
    _patternStartMs = millis();
    _frame = 0;
}

void LEDMatrix::setBrightness(uint8_t level) {
    if (!_initialized) return;
    matrix.setBrightness(level > 15 ? 15 : level);
}

void LEDMatrix::clear() {
    if (!_initialized) return;
    matrix.clear();
}

void LEDMatrix::show() {
    if (!_initialized) return;
    matrix.writeDisplay();
}

void LEDMatrix::fillAll(uint8_t color) {
    for (uint8_t y = 0; y < 8; y++)
        for (uint8_t x = 0; x < 8; x++)
            matrix.drawPixel(x, y, color);
}

void LEDMatrix::drawColumn(uint8_t col, uint8_t color) {
    for (uint8_t y = 0; y < 8; y++)
        matrix.drawPixel(col, y, color);
}

void LEDMatrix::drawPixel(uint8_t x, uint8_t y, uint8_t color) {
    matrix.drawPixel(x, y, color);
}

// --- Pattern renderers ---

void LEDMatrix::renderBoot() {
    // Wipe columns left to right, 100ms per column
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t col = elapsed / 100;
    clear();
    for (uint8_t c = 0; c <= col && c < 8; c++)
        drawColumn(c, LED_YELLOW);
    show();
}

void LEDMatrix::renderPulse(uint8_t color, uint16_t periodMs) {
    // Brightness oscillates using a triangle wave
    uint32_t elapsed = millis() - _patternStartMs;
    uint16_t phase = elapsed % periodMs;
    uint8_t brightness;
    if (phase < periodMs / 2)
        brightness = (phase * 15) / (periodMs / 2);
    else
        brightness = 15 - ((phase - periodMs / 2) * 15) / (periodMs / 2);

    matrix.setBrightness(brightness);
    clear();
    fillAll(color);
    show();
}

void LEDMatrix::renderPixelDrift(uint8_t color) {
    // Single pixel moves slowly across the display
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t pos = (elapsed / 300) % 64;
    uint8_t x = pos % 8;
    uint8_t y = pos / 8;
    clear();
    drawPixel(x, y, color);
    show();
}

void LEDMatrix::renderBlink(uint8_t color, uint16_t periodMs) {
    uint32_t elapsed = millis() - _patternStartMs;
    bool on = ((elapsed / (periodMs / 2)) % 2) == 0;
    clear();
    if (on) fillAll(color);
    show();
}

void LEDMatrix::renderSweep(uint8_t color) {
    // Column sweeps left to right and back
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t pos = (elapsed / 200) % 14;  // 0..13: 0-7 forward, 8-13 = 6..1 back
    uint8_t col = (pos < 8) ? pos : (14 - pos);
    clear();
    drawColumn(col, color);
    show();
}

void LEDMatrix::renderFadeOut(uint8_t color) {
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t brightness = (elapsed < 3000) ? (15 - (elapsed * 15 / 3000)) : 0;
    matrix.setBrightness(brightness);
    clear();
    fillAll(color);
    show();
}

void LEDMatrix::renderRotating(uint8_t color) {
    // Rotating line pattern
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t angle = (elapsed / 150) % 8;
    clear();
    for (uint8_t i = 0; i < 8; i++) {
        uint8_t x, y;
        switch (angle) {
            case 0: x = i; y = 3; break;       // horizontal
            case 1: x = i; y = i; break;       // diagonal
            case 2: x = 3; y = i; break;       // vertical
            case 3: x = 7 - i; y = i; break;   // anti-diagonal
            case 4: x = i; y = 4; break;       // horizontal offset
            case 5: x = i; y = i; break;       // diagonal repeat
            case 6: x = 4; y = i; break;       // vertical offset
            default: x = 7 - i; y = i; break;  // anti-diagonal repeat
        }
        drawPixel(x, y, color);
    }
    show();
}

void LEDMatrix::renderWave(uint8_t color) {
    // Vertical columns with a traveling sine offset
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t offset = (elapsed / 100) % 8;
    clear();
    for (uint8_t x = 0; x < 8; x++) {
        uint8_t height = 3 + 2 * ((x + offset) % 3);  // 3, 5, or 7 pixels high
        uint8_t startY = (8 - height) / 2;
        for (uint8_t y = startY; y < startY + height; y++)
            drawPixel(x, y, color);
    }
    show();
}

// --- Main update dispatcher ---

void LEDMatrix::update() {
    if (!_initialized) return;

    // Throttle updates to ~30fps (33ms)
    uint32_t now = millis();
    if (now - _lastUpdateMs < 33) return;
    _lastUpdateMs = now;

    switch (_pattern) {
        case PAT_OFF:
            clear();
            show();
            break;
        case PAT_BOOT:
            renderBoot();
            break;
        case PAT_ACTIVE:
            renderPulse(LED_GREEN, 2000);
            break;
        case PAT_STANDALONE:
            renderPulse(LED_YELLOW, 2000);
            break;
        case PAT_DEEP_IDLE:
            renderPixelDrift(LED_YELLOW);
            break;
        case PAT_ERROR:
            renderBlink(LED_RED, 500);
            break;
        case PAT_CHARGING:
            renderSweep(LED_RED);
            break;
        case PAT_LOW_BATTERY:
            renderBlink(LED_RED, 300);
            break;
        case PAT_HEALTH_AP:
            renderPulse(LED_GREEN, 2000);
            break;
        case PAT_SHUTDOWN:
            renderFadeOut(LED_RED);
            break;
        case PAT_NAVIGATING:
            renderRotating(LED_GREEN);
            break;
        case PAT_LISTENING:
            renderPulse(LED_GREEN, 500);
            break;
        case PAT_SPEAKING:
            renderWave(LED_YELLOW);
            break;
    }
}
```

- [ ] **Step 3: Update temporary main.cpp**

```cpp
#include <Arduino.h>
#include "battery.h"
#include "power.h"
#include "leds.h"

BatteryMonitor battery;
PowerManager power;
LEDMatrix leds;

void setup() {
    Serial.begin(115200);
    Serial.println("[CORTEX] Booting...");
    leds.begin();
    leds.setPattern(PAT_BOOT);
    power.begin();
    battery.begin();
    leds.setPattern(PAT_STANDALONE);
}

void loop() {
    battery.update();
    power.updateSequence();
    leds.update();
    delay(1);
}
```

- [ ] **Step 4: Build and verify**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 2>&1 | tail -10`

Expected: BUILD SUCCESS.

- [ ] **Step 5: Flash and verify LED + serial**

Run: `pio run -e lolin_d32 --target upload`

Observe:
- Serial should show `[LED] HT16K33 initialized at 0x70.` (or warning if not connected)
- If HT16K33 is connected, the matrix should show the BOOT wipe then STANDALONE yellow pulse

- [ ] **Step 6: Commit**

```bash
git add src/leds.h src/leds.cpp src/main.cpp
git commit -m "feat(cortex): add LEDMatrix module with HT16K33 animations"
```

---

### Task 5: Health Server Module -- health_server.h / health_server.cpp

**Files:**
- Create: `esp32/r2d2_cortex_esp32/src/health_server.h`
- Create: `esp32/r2d2_cortex_esp32/src/health_server.cpp`

Uses the ESP32 built-in WiFi and WebServer libraries (no extra lib_deps needed).

- [ ] **Step 1: Create health_server.h**

Create `esp32/r2d2_cortex_esp32/src/health_server.h`:

```cpp
#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "config.h"
#include "battery.h"
#include "power.h"

class HealthServer {
public:
    void begin(BatteryMonitor* battery, PowerManager* power);
    void update();               // call every loop()
    void enableAP();             // switch to AP mode
    void disableAP();            // back to STA mode
    bool isAPActive() const { return _apActive; }
    bool wakeRequested();        // true once if wake requested via web
    bool sleepRequested();       // true once if sleep requested via web
    void clearWakeRequest() { _wakeRequested = false; }
    void clearSleepRequest() { _sleepRequested = false; }
    String getIP() const;

private:
    BatteryMonitor* _battery = nullptr;
    PowerManager* _power = nullptr;
    WebServer _server{HTTP_PORT};
    bool _apActive = false;
    bool _wifiConnected = false;
    bool _serverStarted = false;
    volatile bool _wakeRequested = false;
    volatile bool _sleepRequested = false;

    void startServer();
    void handleRoot();
    void handleStatus();
    void handleWake();
    void handleSleep();
    String buildHealthPage();
    String buildStatusJson();
};
```

- [ ] **Step 2: Create health_server.cpp**

Create `esp32/r2d2_cortex_esp32/src/health_server.cpp`:

```cpp
#include "health_server.h"

void HealthServer::begin(BatteryMonitor* battery, PowerManager* power) {
    _battery = battery;
    _power = power;

    // Try STA connection
    Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        _wifiConnected = true;
        Serial.printf("[WIFI] Connected. IP=%s\n", WiFi.localIP().toString().c_str());
        startServer();
    } else {
        Serial.println("[WIFI] Connection failed. Continuing offline.");
    }
}

void HealthServer::enableAP() {
    WiFi.disconnect(true);
    delay(100);
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(AP_IP, AP_IP, IPAddress(255, 255, 255, 0));
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    _apActive = true;
    _wifiConnected = false;
    Serial.printf("[WIFI] AP mode: SSID=%s IP=%s\n", AP_SSID, WiFi.softAPIP().toString().c_str());

    if (!_serverStarted) {
        startServer();
    }
}

void HealthServer::disableAP() {
    WiFi.softAPdisconnect(true);
    _apActive = false;
    Serial.println("[WIFI] AP disabled. Reconnecting STA...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(500);
    }
    if (WiFi.status() == WL_CONNECTED) {
        _wifiConnected = true;
        Serial.printf("[WIFI] Reconnected. IP=%s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("[WIFI] Reconnection failed.");
    }
}

String HealthServer::getIP() const {
    if (_apActive) return WiFi.softAPIP().toString();
    if (_wifiConnected) return WiFi.localIP().toString();
    return "N/A";
}

void HealthServer::startServer() {
    _server.on("/", HTTP_GET, [this]() { handleRoot(); });
    _server.on("/status", HTTP_GET, [this]() { handleStatus(); });
    _server.on("/wake", HTTP_POST, [this]() { handleWake(); });
    _server.on("/sleep", HTTP_POST, [this]() { handleSleep(); });
    _server.begin();
    _serverStarted = true;
    Serial.printf("[HTTP] Health server running at http://%s\n", getIP().c_str());
}

void HealthServer::update() {
    if (_serverStarted) {
        _server.handleClient();
    }
}

bool HealthServer::wakeRequested() {
    if (_wakeRequested) {
        _wakeRequested = false;
        return true;
    }
    return false;
}

bool HealthServer::sleepRequested() {
    if (_sleepRequested) {
        _sleepRequested = false;
        return true;
    }
    return false;
}

void HealthServer::handleRoot() {
    _server.send(200, "text/html", buildHealthPage());
}

void HealthServer::handleStatus() {
    _server.send(200, "application/json", buildStatusJson());
}

void HealthServer::handleWake() {
    _wakeRequested = true;
    _server.send(200, "text/plain", "Wake command received.");
}

void HealthServer::handleSleep() {
    _sleepRequested = true;
    _server.send(200, "text/plain", "Sleep command received.");
}

String HealthServer::buildStatusJson() {
    const BatteryData& b = _battery->getData();

    String json = "{";
    json += "\"vbat\":" + String(b.vbat, 2);
    json += ",\"soc\":" + String(b.soc, 1);
    json += ",\"ibat\":" + String(b.ibat, 2);
    json += ",\"temp\":" + String(b.temp, 1);
    json += ",\"mode\":\"" + String(BatteryMonitor::modeName(b.mode)) + "\"";
    json += ",\"alarm\":" + String(b.alarm);
    json += ",\"alarm_name\":\"" + String(BatteryMonitor::alarmName(b.alarm)) + "\"";
    json += ",\"charger\":" + String(b.charger_connected ? "true" : "false");
    json += ",\"pi_on\":" + String(_power->getPiPower() ? "true" : "false");
    json += ",\"motors_on\":" + String(_power->getMD25Power() ? "true" : "false");
    json += ",\"uptime_s\":" + String(millis() / 1000);
    json += ",\"wifi_mode\":\"" + String(_apActive ? "AP" : "STA") + "\"";
    json += ",\"ip\":\"" + getIP() + "\"";
    json += "}";
    return json;
}

String HealthServer::buildHealthPage() {
    const BatteryData& b = _battery->getData();

    String html = R"rawhtml(<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>R2D2 Status</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a2e;color:#e0e0e0;font-family:monospace;padding:16px;max-width:480px;margin:0 auto}
h1{color:#0ff;font-size:1.4em;margin-bottom:12px;text-align:center}
.card{background:#16213e;border-radius:8px;padding:12px;margin-bottom:10px}
.card h2{color:#0af;font-size:1em;margin-bottom:8px}
.row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1a1a3e}
.row:last-child{border:none}
.label{color:#888}.val{color:#0f0;font-weight:bold}
.warn{color:#ff0}.crit{color:#f00}
.btn{display:block;width:100%;padding:12px;margin:6px 0;border:none;border-radius:6px;
font-size:1em;font-family:monospace;cursor:pointer}
.btn-wake{background:#0a5;color:#fff}
.btn-sleep{background:#a00;color:#fff}
.btn:active{opacity:0.7}
.footer{text-align:center;color:#555;font-size:0.8em;margin-top:12px}
</style></head><body>
<h1>R2D2 Cortex Status</h1>
)rawhtml";

    // Battery card
    html += "<div class='card'><h2>Battery</h2>";
    html += "<div class='row'><span class='label'>Voltage</span><span class='val'>" + String(b.vbat, 2) + " V</span></div>";

    String socClass = "val";
    if (b.soc < 20.0f) socClass = "crit";
    else if (b.soc < 50.0f) socClass = "warn";
    html += "<div class='row'><span class='label'>SOC</span><span class='" + socClass + "'>" + String(b.soc, 1) + " %</span></div>";

    html += "<div class='row'><span class='label'>Current</span><span class='val'>" + String(b.ibat, 2) + " A</span></div>";
    html += "<div class='row'><span class='label'>Temperature</span><span class='val'>" + String(b.temp, 1) + " &deg;C</span></div>";
    html += "<div class='row'><span class='label'>Charger</span><span class='val'>" + String(b.charger_connected ? "Connected" : "None") + "</span></div>";
    html += "<div class='row'><span class='label'>Mode</span><span class='val'>" + String(BatteryMonitor::modeName(b.mode)) + "</span></div>";
    html += "<div class='row'><span class='label'>Alarm</span><span class='val'>" + String(BatteryMonitor::alarmName(b.alarm)) + "</span></div>";
    html += "</div>";

    // Power card
    html += "<div class='card'><h2>Power</h2>";
    html += "<div class='row'><span class='label'>Pi</span><span class='val'>" + String(_power->getPiPower() ? "ON" : "OFF") + "</span></div>";
    html += "<div class='row'><span class='label'>Motors</span><span class='val'>" + String(_power->getMD25Power() ? "ON" : "OFF") + "</span></div>";
    html += "</div>";

    // Network card
    html += "<div class='card'><h2>Network</h2>";
    html += "<div class='row'><span class='label'>WiFi Mode</span><span class='val'>" + String(_apActive ? "AP" : "STA") + "</span></div>";
    html += "<div class='row'><span class='label'>IP</span><span class='val'>" + getIP() + "</span></div>";
    html += "<div class='row'><span class='label'>Uptime</span><span class='val'>" + String(millis() / 1000) + " s</span></div>";
    html += "</div>";

    // Control buttons
    html += R"rawhtml(
<form method="POST" action="/wake" onsubmit="return confirm('Wake R2D2?')">
<button class="btn btn-wake" type="submit">Wake R2D2</button></form>
<form method="POST" action="/sleep" onsubmit="return confirm('Put R2D2 to sleep?')">
<button class="btn btn-sleep" type="submit">Sleep R2D2</button></form>
<div class="footer">R2D2 Cortex ESP32 &bull; Auto-refresh 5s</div>
</body></html>)rawhtml";

    return html;
}
```

- [ ] **Step 3: Build**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 2>&1 | tail -10`

Expected: BUILD SUCCESS.

- [ ] **Step 4: Commit**

```bash
git add src/health_server.h src/health_server.cpp
git commit -m "feat(cortex): add HealthServer with WiFi AP/STA and HTTP health page"
```

---

### Task 6: Main State Machine -- main.cpp

**Files:**
- Modify: `esp32/r2d2_cortex_esp32/src/main.cpp`

This replaces the temporary stub with the full state machine including button handling, battery alerts, and status printing.

- [ ] **Step 1: Write the complete main.cpp**

Replace `esp32/r2d2_cortex_esp32/src/main.cpp` with:

```cpp
#include <Arduino.h>
#include "config.h"
#include "battery.h"
#include "power.h"
#include "leds.h"
#include "health_server.h"

// --- State Machine ---
enum CortexState {
    STATE_BOOT,
    STATE_ACTIVE,      // Pi running, micro-ROS connected (future)
    STATE_STANDALONE,  // Pi down, monitoring continues
    STATE_DEEP_IDLE,   // Pi off, everything off
};

static const char* stateName(CortexState s) {
    switch (s) {
        case STATE_BOOT:       return "BOOT";
        case STATE_ACTIVE:     return "ACTIVE";
        case STATE_STANDALONE: return "STANDALONE";
        case STATE_DEEP_IDLE:  return "DEEP_IDLE";
        default:               return "???";
    }
}

// --- Globals ---
BatteryMonitor battery;
PowerManager power;
LEDMatrix leds;
HealthServer healthServer;

CortexState state = STATE_BOOT;
uint32_t lastStatusPrintMs = 0;
bool prevChargerState = false;

// --- Button debounce ---
bool buttonDown = false;
uint32_t buttonDownMs = 0;

static void setState(CortexState newState) {
    if (newState == state) return;
    Serial.printf("[CORTEX] State: %s -> %s\n", stateName(state), stateName(newState));
    state = newState;
}

// --- Button handling (non-blocking) ---
static void handleButton() {
    bool pressed = (digitalRead(PIN_WAKE_BTN) == LOW);

    if (pressed && !buttonDown) {
        // Button just pressed
        buttonDown = true;
        buttonDownMs = millis();
    }

    if (!pressed && buttonDown) {
        // Button just released
        uint32_t duration = millis() - buttonDownMs;
        buttonDown = false;

        if (duration >= BUTTON_LONG_PRESS_MS) {
            // Long press: toggle AP mode
            if (healthServer.isAPActive()) {
                Serial.println("[CORTEX] Long press: disabling AP mode.");
                healthServer.disableAP();
                leds.setPattern(state == STATE_DEEP_IDLE ? PAT_DEEP_IDLE : PAT_STANDALONE);
            } else {
                Serial.println("[CORTEX] Long press: enabling AP mode.");
                healthServer.enableAP();
                leds.setPattern(PAT_HEALTH_AP);
            }
        } else if (duration > 50) {  // debounce
            // Short press: wake if in DEEP_IDLE
            if (state == STATE_DEEP_IDLE) {
                Serial.println("[CORTEX] Short press: waking up.");
                power.startWakeSequence();
            } else {
                Serial.println("[CORTEX] Short press: already awake, ignoring.");
            }
        }
    }
}

// --- Battery alert handling ---
static void handleBatteryAlerts() {
    const BatteryData& b = battery.getData();
    if (!b.valid) return;

    // Charger state change
    if (b.charger_connected && !prevChargerState) {
        Serial.println("[CORTEX] Charger connected. Switching to UPS mode.");
        battery.setMode(2);  // UPS
        leds.setPattern(PAT_CHARGING);
    } else if (!b.charger_connected && prevChargerState) {
        Serial.println("[CORTEX] Charger disconnected. Switching to DCHG mode.");
        battery.setMode(1);  // DCHG
        leds.setPattern(state == STATE_DEEP_IDLE ? PAT_DEEP_IDLE : PAT_STANDALONE);
    }
    prevChargerState = b.charger_connected;

    // SOC alerts (only when not charging)
    if (!b.charger_connected) {
        uint16_t rawSOC = (uint16_t)(b.soc * 10.0f);  // back to raw for threshold compare
        if (rawSOC <= BAT_SOC_CRITICAL) {
            Serial.println("[CORTEX] CRITICAL: SOC below 10%. Forcing shutdown.");
            leds.setPattern(PAT_SHUTDOWN);
            power.startShutdownSequence();
        } else if (rawSOC <= BAT_SOC_LOW) {
            leds.setPattern(PAT_LOW_BATTERY);
        }
    }
}

// --- Serial status print ---
static void printStatus() {
    const BatteryData& b = battery.getData();
    Serial.printf("[STATUS] State=%s VBAT=%.2fV SOC=%.1f%% IBAT=%.2fA TEMP=%.1fC "
                  "Mode=%s Alarm=%s Pi=%s MD25=%s WiFi=%s IP=%s\n",
                  stateName(state), b.vbat, b.soc, b.ibat, b.temp,
                  BatteryMonitor::modeName(b.mode),
                  BatteryMonitor::alarmName(b.alarm),
                  power.getPiPower() ? "ON" : "OFF",
                  power.getMD25Power() ? "ON" : "OFF",
                  healthServer.isAPActive() ? "AP" : "STA",
                  healthServer.getIP().c_str());
}

// --- Arduino entry points ---
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println();
    Serial.println("[CORTEX] Booting...");

    // Button pin
    pinMode(PIN_WAKE_BTN, INPUT_PULLUP);

    // Init modules in order
    leds.begin();
    leds.setPattern(PAT_BOOT);

    power.begin();

    battery.begin();

    healthServer.begin(&battery, &power);

    // Transition to STANDALONE (Pi state unknown at boot)
    setState(STATE_STANDALONE);
    leds.setPattern(PAT_STANDALONE);

    Serial.printf("[CORTEX] Ready. State=%s\n", stateName(state));
}

void loop() {
    // 1. Battery polling
    battery.update();

    // 2. LED animation
    leds.update();

    // 3. HTTP server
    healthServer.update();

    // 4. Power sequence advancement
    power.updateSequence();

    // 5. Button
    handleButton();

    // 6. Web wake/sleep requests
    if (healthServer.wakeRequested() && state == STATE_DEEP_IDLE) {
        Serial.println("[CORTEX] Wake requested via web.");
        power.startWakeSequence();
    }
    if (healthServer.sleepRequested() && state != STATE_DEEP_IDLE) {
        Serial.println("[CORTEX] Sleep requested via web.");
        leds.setPattern(PAT_SHUTDOWN);
        power.startShutdownSequence();
    }

    // 7. Track power sequence completions -> state transitions
    if (!power.isSequenceRunning()) {
        if (state == STATE_STANDALONE && !power.getPiPower() && !power.getMD25Power()) {
            // Just finished a shutdown
            setState(STATE_DEEP_IDLE);
            leds.setPattern(PAT_DEEP_IDLE);
        }
        if (state == STATE_DEEP_IDLE && power.getPiPower()) {
            // Just finished a wake
            setState(STATE_STANDALONE);
            leds.setPattern(PAT_STANDALONE);
        }
    }

    // 8. Battery alerts
    handleBatteryAlerts();

    // 9. Periodic status print
    uint32_t now = millis();
    if (now - lastStatusPrintMs >= STATUS_PRINT_MS) {
        lastStatusPrintMs = now;
        printStatus();
    }
}
```

- [ ] **Step 2: Build**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e lolin_d32 2>&1 | tail -10`

Expected: BUILD SUCCESS.

- [ ] **Step 3: Flash and capture serial output**

Run: `pio run -e lolin_d32 --target upload`

Capture ~15s of serial output:
```bash
python3 -c "
import serial, time
ser = serial.Serial('/dev/cu.usbserial-5AA70048951', 115200, timeout=1)
end = time.time() + 15
while time.time() < end:
    line = ser.readline().decode('utf-8', errors='replace').rstrip()
    if line: print(line)
ser.close()
"
```

Expected output pattern:
```
[CORTEX] Booting...
[LED] HT16K33 initialized at 0x70.
[POWER] WARNING: No DS2413 found on 1-Wire bus. Power control disabled.
[POWER] Initialized. MD25=OFF Pi=OFF
[BAT] Initializing XY-BT13L...
[BAT] Current ALARM=2 (NBE)
[BAT] Mode set to DCHG.
[BAT] DCH_RELAY=1 confirmed.
[BAT] XY-BT13L connected. VBAT=13.13V SOC=49.5% ALARM=NBE(active)
[WIFI] Connecting to YOUR_SSID...
[WIFI] Connection failed. Continuing offline.
[CORTEX] State: BOOT -> STANDALONE
[CORTEX] Ready. State=STANDALONE
[STATUS] State=STANDALONE VBAT=13.13V SOC=49.5% ...
```

(WiFi failure expected with placeholder credentials. DS2413 warning expected if not connected.)

- [ ] **Step 4: Verify register_scan environment still builds**

Run: `cd esp32/r2d2_cortex_esp32 && pio run -e register_scan 2>&1 | tail -5`

Expected: BUILD SUCCESS (register_scan is independent).

- [ ] **Step 5: Commit**

```bash
git add src/main.cpp
git commit -m "feat(cortex): complete state machine with button handling and battery alerts"
```

---

### Task 7: Integration Verification

**Files:** None new -- this is a verification-only task.

- [ ] **Step 1: Full clean build of both environments**

```bash
cd esp32/r2d2_cortex_esp32
pio run -e lolin_d32 -e register_scan 2>&1 | grep -E "(SUCCESS|FAILED|error)"
```

Expected: Both environments build successfully.

- [ ] **Step 2: Flash main firmware and capture extended output**

```bash
pio run -e lolin_d32 --target upload
```

Capture 20s of serial output to verify:
- Boot sequence completes without errors
- Battery data is read every 2s
- Status prints every 10s
- No crashes or reboots

- [ ] **Step 3: Open health page (if WiFi configured)**

If WiFi credentials are real (not placeholder), open the health page URL shown in serial output in a browser. Verify:
- Dark theme renders correctly
- Battery values match serial output
- Wake/Sleep buttons show confirm dialogs
- Auto-refresh updates values every 5 seconds
- `/status` endpoint returns valid JSON

- [ ] **Step 4: Final commit with all files**

Verify nothing is missing:
```bash
git status
git diff --stat
```

Ensure these files are tracked:
- `platformio.ini` (modified)
- `.gitignore` (modified)
- `src/battery.h`, `src/battery.cpp` (new)
- `src/power.h`, `src/power.cpp` (new)
- `src/leds.h`, `src/leds.cpp` (new)
- `src/health_server.h`, `src/health_server.cpp` (new)
- `src/main.cpp` (modified)
- `src/register_scan.cpp` (existing, unchanged)
- `src/config.h` should NOT appear (it's in .gitignore)

If any files need staging:
```bash
git add <files>
git commit -m "feat(cortex): R2D2 Cortex ESP32 full firmware - battery, power, LEDs, health server"
```

---

## Summary

| Task | Module | Key Risk |
|------|--------|----------|
| 1 | Scaffolding | config.h must not be committed |
| 2 | Battery | ModbusMaster buffer overwrite between batch reads |
| 3 | Power | DS2413 inverted logic; safety checks on power sequencing |
| 4 | LEDs | BicolorMatrix color limitations (3 colors, not full RGB) |
| 5 | Health Server | WiFi timeout; large HTML string in PROGMEM-constrained RAM |
| 6 | Main | Non-blocking loop; correct state transitions |
| 7 | Integration | Full system verification |
