#include "oled_display.h"
#include "config.h"
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---- Layout-Konstanten ----------------------------------------
// Font-Size 1 → Zeichen 6×8 px → 21 Zeichen / 8 Zeilen auf 128×64
#define OLED_W          128
#define OLED_H           64
#define LOG_LINES          5   // sichtbare Scroll-Zeilen
#define CHARS_PER_LINE    21   // Zeichen je Zeile (inkl. '\0' → +1)
#define LOG_Y_OFFSET      11   // Pixel-Y des ersten Log-Eintrags
#define LOG_LINE_H        10   // Zeilenhöhe (8 px Glyph + 2 px Abstand)
#define CONNECTED_SHOW_MS 2000 // ms "ROS2 Connected!" einblenden

// ---- Display-Objekt (hardware SPI) ----------------------------
static Adafruit_SSD1306 display(
    OLED_W, OLED_H,
    OLED_MOSI_PIN, OLED_CLK_PIN,
    OLED_DC_PIN, OLED_RST_PIN, OLED_CS_PIN
);

// ---- Interner Zustand -----------------------------------------
enum OledState { OLED_WAITING, OLED_CONNECTED_BRIEF, OLED_LOG };

static OledState  g_state        = OLED_WAITING;
static bool       g_oled_ok      = false;
static unsigned long g_connected_at = 0;

// Kreispuffer: log_buf[log_head] ist der älteste Eintrag
static char  g_log_buf[LOG_LINES][CHARS_PER_LINE + 1];
static uint8_t g_log_head  = 0;
static bool    g_log_dirty = false;

// Letzter Uptime-Wert → Redraw nur bei Änderung
static unsigned long g_last_uptime = ULONG_MAX;

// ---- Zeichenfunktionen ----------------------------------------
static void draw_waiting(unsigned long uptime_s) {
    char buf[24];
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("Waiting for"));
    display.println(F("ROS2 agent..."));
    display.println();
    snprintf(buf, sizeof(buf), "Uptime: %lus", uptime_s);
    display.print(buf);
    display.display();
}

static void draw_connected_brief() {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 24);
    display.println(F("  ROS2 Connected!"));
    display.display();
}

static void draw_log() {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    // Header + Trennlinie
    display.setCursor(0, 0);
    display.print(F("/rosout"));
    display.drawFastHLine(0, 9, OLED_W, SSD1306_WHITE);

    // Log-Zeilen: älteste oben, neueste unten
    for (uint8_t i = 0; i < LOG_LINES; i++) {
        uint8_t idx = (g_log_head + i) % LOG_LINES;
        display.setCursor(0, LOG_Y_OFFSET + i * LOG_LINE_H);
        display.print(g_log_buf[idx]);
    }
    display.display();
    g_log_dirty = false;
}

// ---- Öffentliche API ------------------------------------------
bool oled_init() {
    // SSD1306_SWITCHCAPVCC = interner Ladepumpen-Boost (3.3 V Betrieb)
    if (!display.begin(SSD1306_SWITCHCAPVCC)) {
        Serial.println(F("[OLED] SSD1306 nicht gefunden – Display deaktiviert."));
        g_oled_ok = false;
        return false;
    }
    g_oled_ok = true;
    memset(g_log_buf, 0, sizeof(g_log_buf));

    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("R2D2 Chassis"));
    display.println(F("Booting..."));
    display.display();

    Serial.println(F("[OLED] SSD1306 initialisiert."));
    return true;
}

void oled_push_log(const char* text) {
    if (!g_oled_ok || !text) return;
    strncpy(g_log_buf[g_log_head], text, CHARS_PER_LINE);
    g_log_buf[g_log_head][CHARS_PER_LINE] = '\0';
    g_log_head = (g_log_head + 1) % LOG_LINES;
    g_log_dirty = true;
}

void oled_update(bool connected, unsigned long uptime_s) {
    if (!g_oled_ok) return;

    // --- Getrennt / Reconnect ---
    if (!connected) {
        if (g_state != OLED_WAITING) {
            g_state       = OLED_WAITING;
            g_last_uptime = ULONG_MAX;  // sofortiger Redraw
        }
        if (uptime_s != g_last_uptime) {
            g_last_uptime = uptime_s;
            draw_waiting(uptime_s);
        }
        return;
    }

    // --- Verbunden ---
    if (g_state == OLED_WAITING) {
        g_state        = OLED_CONNECTED_BRIEF;
        g_connected_at = millis();
        draw_connected_brief();
        return;
    }

    if (g_state == OLED_CONNECTED_BRIEF) {
        if (millis() - g_connected_at >= CONNECTED_SHOW_MS) {
            g_state = OLED_LOG;
            draw_log();          // erstes Log-Bild (ggf. leer)
        }
        return;
    }

    // --- Log-Anzeige: nur bei neuen Einträgen neuzeichnen ---
    if (g_log_dirty) {
        draw_log();
    }
}
