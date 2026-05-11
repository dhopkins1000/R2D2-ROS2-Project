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
