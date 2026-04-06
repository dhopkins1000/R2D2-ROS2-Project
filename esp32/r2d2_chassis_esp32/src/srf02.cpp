#include "srf02.h"
#include "config.h"
#include <Wire.h>

void srf02_trigger() {
    Wire.beginTransmission(ULTRASONIC_ADDR);
    Wire.write(0x00);   // Command register
    Wire.write(0x51);   // Range in cm
    Wire.endTransmission();
}

bool srf02_read_cm(uint16_t* dist_cm) {
    Wire.beginTransmission(ULTRASONIC_ADDR);
    Wire.write(0x02);   // Range result high byte
    if (Wire.endTransmission() != 0) return false;

    if (Wire.requestFrom((uint8_t)ULTRASONIC_ADDR, (uint8_t)2) != 2) return false;

    *dist_cm = (uint16_t)(Wire.read() << 8 | Wire.read());
    return true;
}
