# Cortex ESP32 – Power Controller & Status Indicator

## Konzept

Ein dedizierter ESP32 der **immer aktiv** ist (~0.05W) und zwei Aufgaben hat:
1. **Power Management** – steuert alle Stromkreise via DS2413 + MOSFETs
2. **Visual Status Indicator** – zeigt R2D2's Zustand über RGB Matrix

## Hardware

```
Cortex ESP32 (LOLIN D32)
  ├── HT16K33 8x8 RGB Matrix  (I2C)      ← Status Indicator
  ├── DS2413 #1               (1-Wire)   ← Dual Power Switch
  │     ├── Channel A → IRLZ44N N-FET   ← 12V MD25 GND-side
  │     └── Channel B → IRF4905 P-FET   ← 5V Pi VCC-side
  ├── Wake Button              (GPIO)    ← Wake from deep idle
  └── (optional) 1-Wire Bus expansion   ← weitere DS2413 falls nötig
```

Die Pi-Stromversorgung schaltet den gesamten Pi-USB-Bus mit:
Xtion Pro, Webcam, ReSpeaker, Chassis ESP32 (via Hub) — alle gehen
gemeinsam mit dem Pi hoch und runter.

Für feingranulare USB-Steuerung (Xtion/Webcam einzeln) nutzt der Pi
`uhubctl` auf seinen eigenen VL805-Ports. Das ist reine Software, kein
zusätzliches Hardware-Switching.

Siehe [power_management.md](power_management.md) für vollständige
Schaltplan-Details zum DS2413 + MOSFET Circuit.

## RGB Matrix – Status Zustände

| Zustand | Farbe | Animation | Beschreibung |
|---|---|---|---|
| Boot | Weiß | Wipe von links nach rechts | System startet |
| Active / Wach | Blau | Langsam pulsieren | R2D2 ist aktiv |
| Navigating | Grün | Rotation / Sweep | Fährt / navigiert |
| Listening | Cyan | Schnelles Pulsieren | Wake Word erkannt |
| Speaking | Gelb | Wellen-Animation | TTS aktiv |
| Idle | Gelb/Orange | Sehr langsames Glimmen | Wartemodus |
| Deep Idle | Orange | Einzelne Pixel, sehr langsam | Pi aus, nur Cortex aktiv |
| Error | Rot | Blinken | Fehler / Watchdog |
| Charging | Violett | Langsamer Sweep | Am Ladekabel |
| Shutdown | Rot | Fade out | System fährt herunter |

## ROS2 Topic Interface

Der Cortex verbindet sich per **WiFi + micro-ROS** mit dem Pi (gleicher
Reconnect-Loop Pattern wie der Chassis ESP32). Wenn der Pi aus ist, läuft
der Cortex standalone im Deep-Idle-Modus und wartet auf Wake-Signal.

```
/r2d2/power/state   (std_msgs/String) → empfangen vom Pi
  Mögliche Werte:
    "active"         → Blau pulsierend
    "navigating"     → Grün rotating
    "listening"      → Cyan pulsierend
    "speaking"       → Gelb Wellen
    "idle"           → Orange glimmen
    "shutdown"       → Rot fade out → Shutdown Sequenz auslösen
    "error"          → Rot blinken
    "charging"       → Violett sweep

/r2d2/cortex/leds   (std_msgs/String, JSON) → direkte LED-Steuerung
  Beispiel: {"pattern": "pulse", "color": [0,0,255], "speed": "slow"}
```

## Power Management

### DS2413 Firmware (Cortex)

```cpp
// Libraries: OneWire + DS2413 (Arduino)
// DS2413 Channel A = MD25 (active = motor power on)
// DS2413 Channel B = Pi   (active = Pi power on)
// Note: DS2413 open-drain LOW activates the NPN → MOSFET ON
// Logic convention in firmware: true = powered, false = off

void setPower(bool md25, bool pi) {
    ds2413.setOutput(
        !md25,   // Ch.A: inverted (low = on)
        !pi      // Ch.B: inverted (low = on)
    );
}
```

### Shutdown Sequenz

```
1. Pi publiziert /r2d2/power/state: "shutdown"
2. Cortex zeigt Rot fade-out Animation
3. Pi GPIO geht LOW (sudo shutdown -h now)
4. Cortex wartet 10s (Pi fährt runter)
5. DS2413 Ch.B → HIGH → P-FET sperrt → Pi 5V aus
   (schaltet gleichzeitig: Pi, Xtion, Webcam, ReSpeaker, Hub, Chassis ESP32)
6. DS2413 Ch.A → HIGH → N-FET sperrt → MD25 aus (falls noch aktiv)
7. Cortex wechselt zu Deep Idle Animation (orange, sehr langsam)
8. Nur Cortex aktiv, wartet auf Wake-Signal
```

### Wake Sequenz

```
1. Wake-Signal: physischer Knopf an Cortex GPIO ODER Timer-Interrupt
2. Cortex zeigt Boot Animation (weiß, wipe)
3. DS2413 Ch.A → LOW → MD25 Relay vorbereitet (optional, erst bei Fahrt)
4. DS2413 Ch.B → LOW → P-FET leitet → Pi 5V ein
5. Pi bootet, r2d2.service startet automatisch
6. micro-ROS Agent auf Pi startet
7. Cortex reconnectet zum micro-ROS Agent (Reconnect-Loop)
8. Pi publiziert /r2d2/power/state: "active"
9. Cortex wechselt zu Blau pulsierend
```

### Watchdog

```
Cortex überwacht /r2d2/power/state Heartbeat (oder /r2d2/chassis/status)
→ kein Signal für >30s → Rot blinken, Warnung loggen
→ kein Signal für >60s → Hard Power Cycle via DS2413
   (Ch.B HIGH → 5s warten → Ch.B LOW → Pi neu gestartet)
```

## Wake aus Deep Idle: Mechanismen

| Mechanismus | Unterstützt | Details |
|---|---|---|
| Physischer Knopf | ✅ | GPIO an Cortex, interrupt-driven |
| Timer (täglich/geplant) | ✅ | ESP32 RTC oder Software-Timer |
| Wake Word (Stimme) | ❌ | ReSpeaker braucht Pi – nicht möglich in Deep Idle |

Voice Wake ist in allen anderen States verfügbar (Voice-only idle, Navigation
idle, Full active). Deep Idle ist nur für "wirklich aus" — manuelle oder
geplante Aktivierung.

## Warum Cortex und nicht Head ESP32?

Die 8x8 RGB Matrix war ursprünglich für den Head ESP32 geplant.
Sie sitzt am Cortex weil:

- **Immer sichtbar**: Status auch wenn Pi aus ist (Deep Idle)
- **Unabhängig**: kein ROS2 nötig für Basis-Status
- **Sicherheit**: Fehler und Shutdown-Status immer anzeigbar
- **Einfacher**: Head ESP32 wird schlanker

Der Head ESP32 behält SerLCD 40x2 für Text-Output und Ultraschall-Sensor.
