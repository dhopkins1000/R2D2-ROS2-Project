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
