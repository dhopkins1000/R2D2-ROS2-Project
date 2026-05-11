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
