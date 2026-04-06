#include "hmc5883l.h"
#include "config.h"
#include <Wire.h>

// Default gain ±1.3 Ga → 1090 LSB/Gauss, 1 Gauss = 1e-4 Tesla
static constexpr float LSB_TO_TESLA = 1.0f / 1090.0f * 1e-4f;

bool hmc5883l_init() {
    // Config Register A: 8-sample avg, 15 Hz output rate, normal measurement
    Wire.beginTransmission(HMC5883L_ADDR);
    Wire.write(0x00);
    Wire.write(0x70);
    if (Wire.endTransmission() != 0) return false;

    // Config Register B: gain ±1.3 Ga (0x20)
    Wire.beginTransmission(HMC5883L_ADDR);
    Wire.write(0x01);
    Wire.write(0x20);
    if (Wire.endTransmission() != 0) return false;

    // Mode Register: continuous measurement mode
    Wire.beginTransmission(HMC5883L_ADDR);
    Wire.write(0x02);
    Wire.write(0x00);
    if (Wire.endTransmission() != 0) return false;

    return true;
}

bool hmc5883l_read(float* x_T, float* y_T, float* z_T) {
    Wire.beginTransmission(HMC5883L_ADDR);
    Wire.write(0x03);
    if (Wire.endTransmission() != 0) return false;

    if (Wire.requestFrom((uint8_t)HMC5883L_ADDR, (uint8_t)6) != 6) return false;

    // HMC5883L register order: X_H, X_L, Z_H, Z_L, Y_H, Y_L
    int16_t raw_x = (int16_t)(Wire.read() << 8 | Wire.read());
    int16_t raw_z = (int16_t)(Wire.read() << 8 | Wire.read());
    int16_t raw_y = (int16_t)(Wire.read() << 8 | Wire.read());

    *x_T = raw_x * LSB_TO_TESLA;
    *y_T = raw_y * LSB_TO_TESLA;
    *z_T = raw_z * LSB_TO_TESLA;

    return true;
}
