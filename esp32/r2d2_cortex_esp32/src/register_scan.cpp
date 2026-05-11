#include <Arduino.h>
#include <ModbusMaster.h>

// UART2 pins for XY-BT13L Modbus RTU
static constexpr uint8_t MODBUS_RX = 16;
static constexpr uint8_t MODBUS_TX = 17;
static constexpr uint8_t SLAVE_ADDR = 1;

ModbusMaster node;

// Known register names
const char* regName(uint16_t addr) {
    switch (addr) {
        case 0x00: return "MODE";
        case 0x01: return "CH_RELAY";
        case 0x02: return "DCH_RELAY";
        case 0x03: return "AH_LOW";
        case 0x04: return "AH_HIGH";
        case 0x05: return "WH_LOW";
        case 0x06: return "WH_HIGH";
        case 0x07: return "PER (%)";
        case 0x08: return "VCHARGE (V, /100)";
        case 0x09: return "VBAT (V, /100)";
        case 0x0A: return "IBAT (A, /100)";
        case 0x0B: return "W_LOW";
        case 0x0C: return "W_HIGH";
        case 0x0D: return "CH_Runtime (min)";
        case 0x0E: return "DCH_Runtime (min)";
        case 0x0F: return "LOOPCOUNT";
        case 0x10: return "IN_TEMP (°C)";
        case 0x11: return "EX_TEMP (°C)";
        case 0x12: return "ALARM";
        case 0x13: return "STOP";
        case 0x14: return "LEARN";
        case 0x15: return "CAP (Ah)";
        case 0x16: return "LBP (%)";
        case 0x17: return "LVP (V)";
        case 0x18: return "OVP (V)";
        case 0x19: return "LAP (A)";
        case 0x1A: return "OCP (A)";
        default:   return nullptr;
    }
}

// Track which registers responded
static uint16_t lastRespondingAddr = 0;
static uint16_t totalRead = 0;
static bool     scanDone = false;

void printRegister(uint16_t addr, uint16_t raw) {
    const char* name = regName(addr);
    if (name) {
        Serial.printf("  REG 0x%04X = %5u  (0x%04X)  <%s>\n", addr, raw, raw, name);
    } else {
        Serial.printf("  REG 0x%04X = %5u  (0x%04X)\n", addr, raw, raw);
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) { ; }

    Serial2.begin(115200, SERIAL_8N1, MODBUS_RX, MODBUS_TX);
    node.begin(SLAVE_ADDR, Serial2);

    Serial.println();
    Serial.println("=== XY-BT13L Full Register Scan ===");
    Serial.println("Scanning holding registers 0x0000..0x00FF (FC 0x03)");
    Serial.println("Batch size: 16 registers, 50ms gap between batches");
    Serial.println();

    uint16_t firstNonResponding = 0xFFFF;

    for (uint16_t base = 0x0000; base <= 0x00F0; base += 16) {
        uint16_t count = 16;

        uint8_t result = node.readHoldingRegisters(base, count);

        if (result == node.ku8MBSuccess) {
            for (uint16_t i = 0; i < count; i++) {
                uint16_t raw = node.getResponseBuffer(i);
                printRegister(base + i, raw);
                lastRespondingAddr = base + i;
                totalRead++;
            }
        } else {
            for (uint16_t i = 0; i < count; i++) {
                Serial.printf("  REG 0x%04X = [NO RESPONSE]\n", base + i);
            }
            if (firstNonResponding == 0xFFFF) {
                firstNonResponding = base;
            }
        }

        delay(50);
    }

    Serial.println();
    Serial.println("--- SCAN COMPLETE ---");
    Serial.printf("Responding registers: 0x0000 - 0x%04X\n", lastRespondingAddr);
    if (firstNonResponding != 0xFFFF) {
        Serial.printf("First non-responding address: 0x%04X\n", firstNonResponding);
    }
    Serial.printf("Total registers read: %u\n", totalRead);
    Serial.println();
    Serial.println("=== Starting live refresh of responding registers ===");
    Serial.println();

    scanDone = true;
}

void loop() {
    if (!scanDone) return;

    delay(5000);

    Serial.printf("--- Live update (millis=%lu) ---\n", millis());

    // Re-read only the responding range in batches of 16
    for (uint16_t base = 0x0000; base <= lastRespondingAddr; base += 16) {
        uint16_t count = 16;
        if (base + count - 1 > lastRespondingAddr) {
            count = lastRespondingAddr - base + 1;
        }

        uint8_t result = node.readHoldingRegisters(base, count);

        if (result == node.ku8MBSuccess) {
            for (uint16_t i = 0; i < count; i++) {
                uint16_t raw = node.getResponseBuffer(i);
                printRegister(base + i, raw);
            }
        } else {
            Serial.printf("  0x%04X..0x%04X: READ FAILED (0x%02X)\n",
                          base, base + count - 1, result);
        }

        delay(50);
    }
    Serial.println();
}
