# Cortex ESP32 – Power Controller & Status Indicator

## Konzept

Ein dedizierter ESP32 der **immer aktiv** ist (~0.05W) und zwei Aufgaben hat:
1. **Power Management** – steuert alle Stromkreise
2. **Visual Status Indicator** – zeigt R2D2's Zustand über RGB Matrix

## Hardware

```
Cortex ESP32 (LOLIN D32)
  ├── HT16K33 8x8 RGB Matrix  (I2C) ← Status Indicator
  ├── Relay 1                 (GPIO) ← 12V MD25
  ├── Relay 2                 (GPIO) ← 5V Powered USB Hub
  ├── Pi Power Enable         (GPIO) ← 5V Pi
  └── Pi Shutdown Monitor     (GPIO) ← liest Pi GPIO beim Shutdown
```

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

```
/r2d2/power/state   (String) → Cortex ESP32
  Mögliche Werte:
    "active"         → Blau pulsierend
    "navigating"     → Grün rotating
    "listening"      → Cyan pulsierend
    "speaking"       → Gelb Wellen
    "idle"           → Orange glimmen
    "shutdown"       → Rot fade out
    "error"          → Rot blinken
    "charging"       → Violett sweep

/r2d2/cortex/leds   (String, JSON) → direkte LED-Steuerung
  Beispiel: {"pattern": "pulse", "color": [0,0,255], "speed": "slow"}
```

## Power Management

Siehe [power_management.md](power_management.md) für vollständige Details.

### Shutdown Sequenz
```
1. Pi published /r2d2/power/state: "shutdown"
2. Cortex zeigt Rot fade-out Animation
3. Pi GPIO geht LOW (sudo shutdown)
4. Cortex wartet 10s
5. Cortex öffnet Relay 2 (USB Hub)
6. Cortex öffnet Relay 1 (MD25)
7. Cortex öffnet Pi Power Relay
8. Nur Cortex aktiv → Deep Idle Animation
```

### Wake Sequenz
```
1. Wake Signal (Knopf / Timer / ReSpeaker direkt)
2. Cortex zeigt Boot Animation (weiß, wipe)
3. Cortex schließt Pi Power Relay
4. Cortex schließt Relay 2 (USB Hub)
5. Pi bootet, r2d2.service startet automatisch
6. Pi published /r2d2/power/state: "active"
7. Cortex wechselt zu Blau pulsierend
```

### Watchdog
```
Cortex überwacht /r2d2/chassis/status Heartbeat
→ kein Signal für >30s → Rot blinken + Pi Reboot
→ kein Signal für >60s → Hard Power Cycle
```

## Warum RGB Matrix am Cortex statt am Head ESP32?

Die 8x8 RGB Matrix war ursprünglich für den Head ESP32 geplant.
Sie wird zum Cortex verschoben weil:

- **Immer sichtbar**: Status auch wenn Pi aus ist (Deep Idle)
- **Unabhängig**: kein ROS2 nötig für Basis-Status
- **Sicherheit**: Fehler und Shutdown-Status immer anzeigbar
- **Einfacher**: Head ESP32 wird schlanker

Der Head ESP32 behält SerLCD 40x2 für Text-Output und Ultraschall.
