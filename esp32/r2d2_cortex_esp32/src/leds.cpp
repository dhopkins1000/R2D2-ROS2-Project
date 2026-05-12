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
        Serial.printf("[LED] HT16K33 initialized at 0x%02X.\n", HT16K33_ADDR);
    } else {
        Serial.printf("[LED] WARNING: HT16K33 not found at 0x%02X. LED display disabled.\n", HT16K33_ADDR);
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
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t col = elapsed / 100;
    clear();
    for (uint8_t c = 0; c <= col && c < 8; c++)
        drawColumn(c, LED_YELLOW);
    show();
}

void LEDMatrix::renderPulse(uint8_t color, uint16_t periodMs) {
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
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t pos = (elapsed / 200) % 14;
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
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t angle = (elapsed / 150) % 8;
    clear();
    for (uint8_t i = 0; i < 8; i++) {
        uint8_t x, y;
        switch (angle) {
            case 0: x = i; y = 3; break;
            case 1: x = i; y = i; break;
            case 2: x = 3; y = i; break;
            case 3: x = 7 - i; y = i; break;
            case 4: x = i; y = 4; break;
            case 5: x = i; y = i; break;
            case 6: x = 4; y = i; break;
            default: x = 7 - i; y = i; break;
        }
        drawPixel(x, y, color);
    }
    show();
}

void LEDMatrix::renderWave(uint8_t color) {
    uint32_t elapsed = millis() - _patternStartMs;
    uint8_t offset = (elapsed / 100) % 8;
    clear();
    for (uint8_t x = 0; x < 8; x++) {
        uint8_t height = 3 + 2 * ((x + offset) % 3);
        uint8_t startY = (8 - height) / 2;
        for (uint8_t y = startY; y < startY + height; y++)
            drawPixel(x, y, color);
    }
    show();
}

// --- Main update dispatcher ---

void LEDMatrix::update() {
    if (!_initialized) return;

    uint32_t now = millis();
    if (now - _lastUpdateMs < 33) return;
    _lastUpdateMs = now;

    switch (_pattern) {
        case PAT_OFF:        clear(); show(); break;
        case PAT_BOOT:       renderBoot(); break;
        case PAT_ACTIVE:     renderPulse(LED_GREEN, 2000); break;
        case PAT_STANDALONE: renderPulse(LED_YELLOW, 2000); break;
        case PAT_DEEP_IDLE:  renderPixelDrift(LED_YELLOW); break;
        case PAT_ERROR:      renderBlink(LED_RED, 500); break;
        case PAT_CHARGING:   renderSweep(LED_RED); break;
        case PAT_LOW_BATTERY:renderBlink(LED_RED, 300); break;
        case PAT_HEALTH_AP:  renderPulse(LED_GREEN, 2000); break;
        case PAT_SHUTDOWN:   renderFadeOut(LED_RED); break;
        case PAT_NAVIGATING: renderRotating(LED_GREEN); break;
        case PAT_LISTENING:  renderPulse(LED_GREEN, 500); break;
        case PAT_SPEAKING:   renderWave(LED_YELLOW); break;
    }
}
