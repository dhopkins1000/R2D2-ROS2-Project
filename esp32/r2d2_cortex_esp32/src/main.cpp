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
bool shutdownRequested = false;
bool wakeRequested = false;

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
                wakeRequested = true;
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
            shutdownRequested = true;
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
        wakeRequested = true;
        power.startWakeSequence();
    }
    if (healthServer.sleepRequested() && state != STATE_DEEP_IDLE) {
        Serial.println("[CORTEX] Sleep requested via web.");
        shutdownRequested = true;
        leds.setPattern(PAT_SHUTDOWN);
        power.startShutdownSequence();
    }

    // 7. Track power sequence completions -> state transitions
    // Only transition if a sequence was actually requested (prevents
    // spurious STANDALONE->DEEP_IDLE when no DS2413 is connected)
    if (!power.isSequenceRunning()) {
        if (shutdownRequested && state == STATE_STANDALONE) {
            shutdownRequested = false;
            setState(STATE_DEEP_IDLE);
            leds.setPattern(PAT_DEEP_IDLE);
        }
        if (wakeRequested && state == STATE_DEEP_IDLE) {
            wakeRequested = false;
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
