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
    // Important: save values to locals before issuing batch 2 -- ModbusMaster
    // reuses a single response buffer that gets overwritten on each call.
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

    // Batch 2: registers 0x0007..0x0012 (SOC through ALARM)
    uint8_t r2 = _node.readHoldingRegisters(REG_PER, 12);
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
