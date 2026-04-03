#pragma once
#include <Arduino.h>

// OLED initialisieren – muss einmalig in setup() aufgerufen werden.
// Gibt false zurück und loggt über Serial, falls Display nicht gefunden.
bool oled_init();

// Zustand aktualisieren und Display ggf. neu zeichnen (non-blocking).
// connected  = true wenn micro-ROS Agent verbunden
// uptime_s   = millis()/1000 (für Waiting-Screen)
void oled_update(bool connected, unsigned long uptime_s);

// Neue Log-Zeile ans Ende des Scroll-Puffers anfügen.
// Wird aus dem /rosout Subscriber-Callback aufgerufen.
void oled_push_log(const char* text);
