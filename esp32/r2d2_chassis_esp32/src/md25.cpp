#include "md25.h"
#include "config.h"
#include <Arduino.h>

static constexpr double WHEEL_BASE_M = 0.30;  // Spurbreite [m] – an Chassis anpassen
static constexpr double MAX_SPEED_MS = 0.50;  // Maximale Radgeschwindigkeit [m/s]

void md25_init() {
    MD25_UART.begin(MD25_BAUD, SERIAL_8N2, MD25_RX_PIN, MD25_TX_PIN);
    delay(100);
    // DISABLE TIMEOUT: MD25 stoppt sonst nach 2s ohne Kommando
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x38);
    MD25_UART.flush();
    delay(10);
    // RESET ENCODERS: bei jedem Boot bei 0 starten
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x35);
    MD25_UART.flush();
}

void md25_set_speeds(uint8_t speed1, uint8_t speed2) {
    // SET SPEED1: [0x00, 0x31, value]
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x31);
    MD25_UART.write(speed1);
    // SET SPEED2: [0x00, 0x32, value]
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x32);
    MD25_UART.write(speed2);
    MD25_UART.flush();
}

bool md25_get_encoders(int32_t* enc1, int32_t* enc2) {
    while (MD25_UART.available()) MD25_UART.read();  // Puffer leeren
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x25);
    MD25_UART.flush();

    // 8 Bytes warten (bis zu 100ms)
    unsigned long t0 = millis();
    while (MD25_UART.available() < 8 && millis() - t0 < 100);
    if (MD25_UART.available() < 8) return false;

    uint8_t buf[8];
    for (uint8_t i = 0; i < 8; i++) buf[i] = MD25_UART.read();

    *enc1 = (int32_t)((uint32_t)buf[0] << 24 | (uint32_t)buf[1] << 16 |
                      (uint32_t)buf[2] <<  8 | (uint32_t)buf[3]);
    *enc2 = (int32_t)((uint32_t)buf[4] << 24 | (uint32_t)buf[5] << 16 |
                      (uint32_t)buf[6] <<  8 | (uint32_t)buf[7]);
    return true;
}

uint8_t md25_get_version() {
    while (MD25_UART.available()) MD25_UART.read();  // Puffer leeren
    MD25_UART.write((uint8_t)0x00);
    MD25_UART.write((uint8_t)0x29);
    MD25_UART.flush();
    unsigned long t0 = millis();
    while (!MD25_UART.available() && millis() - t0 < 100);
    return MD25_UART.available() ? MD25_UART.read() : 0;
}

void md25_stop() {
    md25_set_speeds(128, 128);
}

void md25_cmd_vel(double linear_x, double angular_z) {
    // Differentialantrieb: v_l = v - ω*(L/2), v_r = v + ω*(L/2)
    double v_left  = linear_x - angular_z * (WHEEL_BASE_M / 2.0);
    double v_right = linear_x + angular_z * (WHEEL_BASE_M / 2.0);

    // Auf [-1, 1] normieren und begrenzen
    double l = v_left  / MAX_SPEED_MS;
    double r = v_right / MAX_SPEED_MS;
    if (l >  1.0) l =  1.0;
    if (l < -1.0) l = -1.0;
    if (r >  1.0) r =  1.0;
    if (r < -1.0) r = -1.0;

    // MD25-Wertebereich: 0=voll rückwärts, 128=Stillstand, 255=voll vorwärts
    uint8_t s1 = (uint8_t)(128 + (int8_t)(l * 127.0));
    uint8_t s2 = (uint8_t)(128 + (int8_t)(r * 127.0));

    md25_set_speeds(s1, s2);
}
