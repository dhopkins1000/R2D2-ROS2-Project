# Cortex ESP32 – Power Controller & Status Indicator

## Konzept

Ein dedizierter ESP32 der **immer aktiv** ist (~0.05W) und drei Aufgaben hat:
1. **Power Management** – steuert alle Stromkreise via DS2413 + MOSFETs
2. **Battery Monitoring** – liest XY-BT13L via UART (Modbus RTU)
3. **Visual Status Indicator** – zeigt R2D2's Zustand über RGB Matrix

## Hardware

```
Cortex ESP32 (LOLIN D32)
  ├── HT16K33 8x8 RGB Matrix  (I2C, GPIO21/22)  ← Status Indicator
  ├── DS2413 #1               (1-Wire)           ← Dual Power Switch
  │     ├── Channel A → IRLZ44N N-FET           ← 12V MD25 GND-side
  │     └── Channel B → IRF4905 P-FET           ← 5V Pi VCC-side
  ├── XY-BT13L Battery Manager (UART2, GPIO16/17) ← Battery Monitoring
  └── Wake Button              (GPIO)            ← Wake from deep idle
```

Die Pi-Stromversorgung schaltet den gesamten Pi-USB-Bus mit:
Xtion Pro, Webcam, ReSpeaker, Chassis ESP32 (via Hub) — alle gehen
gemeinsam mit dem Pi hoch und runter.

Für feingranulare USB-Steuerung (Xtion/Webcam einzeln) nutzt der Pi
`uhubctl` auf seinen eigenen VL805-Ports. Das ist reine Software, kein
zusätzliches Hardware-Switching.

Siehe [power_management.md](power_management.md) für vollständige
Schaltplan-Details zum DS2413 + MOSFET Circuit.

---

## Battery Management (XY-BT13L)

### Hardware

Das XY-BT13L ist ein 30A Battery Management Modul (10–110V) mit integriertem
Coulomb Counter, Lade-/Entladerelais, OVP/LVP/OCP/OTP Schutz und einem
**TTL-seriellen Modbus RTU Interface**.

**Kein RS485-Adapter nötig** — das Modul spricht direkt TTL UART,
kompatibel mit dem ESP32's 3.3V UART.

```
Cortex ESP32                    XY-BT13L
  GPIO17 (UART2 TX) ──────────→ Serial RX
  GPIO16 (UART2 RX) ←────────── Serial TX
  GND               ──────────── GND
```

**Modbus Parameter (Werkseinstellung):**
- Baud Rate: 115200
- Format: 8N1 (kein Parity, 1 Stop Bit)
- Slave Adresse: 1

### Wiring — Strompfad

```
Akku (BT+/BT-) ──→ XY-BT13L ──→ System (OUT+/OUT-)
Ladegerät (IN+/IN-) ──→ XY-BT13L
```

Das XY-BT13L sitzt als Gateway zwischen Akku, Ladegerät und Last.
Es verwaltet Lade- und Entladerelais eigenständig nach konfigurierten
Schwellwerten.

### UPS Mode — Laden während Betrieb

Im UPS-Modus sind beide Relais (Laden + Entladen) gleichzeitig geschlossen.
Das Ladegerät versorgt die Last **und** lädt den Akku parallel.
Bei Ausfall des Ladegeräts übernimmt der Akku nahtlos — kein Reboot nötig.

**Für R2D2 ideal:** Während des Dockens an der Ladestation läuft der
Roboter einfach weiter. Kein Shutdown, keine Unterbrechung.

UPS Mode wird beim Andocken per Modbus aktiviert (Register 0x0000 = 2).

### Modbus Registersatz

Alle Register sind 16-bit (2 Bytes). Kapazität (AH) und Energie (WH)
sind 32-bit und verteilen sich auf zwei aufeinanderfolgende Register (LOW/HIGH).

| Adresse (Hex) | Name        | R/W | Einheit | Beschreibung                        |
|---------------|-------------|-----|---------|-------------------------------------|
| 0x0000        | MODE        | R/W | -       | 0=Charge, 1=Discharge, 2=UPS        |
| 0x0001        | CH_RELAY    | R   | -       | Laderelais Status                   |
| 0x0002        | DCH_RELAY   | R   | -       | Entladerelais Status                |
| 0x0003        | AH_LOW      | R   | mAh     | Verbleibende Kapazität (low 16 bit) |
| 0x0004        | AH_HIGH     | R   | mAh     | Verbleibende Kapazität (high 16 bit)|
| 0x0005        | WH_LOW      | R   | mWh     | Verbleibende Energie (low 16 bit)   |
| 0x0006        | WH_HIGH     | R   | mWh     | Verbleibende Energie (high 16 bit)  |
| 0x0007        | PER         | R   | %       | State of Charge (SOC)               |
| 0x0008        | VCHARGE     | R   | V       | Ladegerät-Spannung                  |
| 0x0009        | VBAT        | R   | V       | Batteriespannung                    |
| 0x000A        | IBAT        | R   | A       | Batteriestrom                       |
| 0x000B        | W_LOW       | R   | mW      | Leistung (low 16 bit)               |
| 0x000C        | W_HIGH      | R   | mW      | Leistung (high 16 bit)              |
| 0x000D        | CH_Runtime  | R   | Min     | Laufzeit Laden                      |
| 0x000E        | DCH_Runtime | R   | Min     | Laufzeit Entladen                   |
| 0x000F        | LOOPCOUNT   | R   | -       | Anzahl Ladezyklen                   |
| 0x0010        | IN_TEMP     | R   | °C      | Boardtemperatur                     |
| 0x0011        | EX_TEMP     | R   | °C      | Externe Temperatur (NTC Probe)      |
| 0x0012        | ALARM       | R/W | -       | Alarmstatus                         |
| 0x0013        | STOP        | R/W | -       | Mode Pause                          |
| 0x0015        | CAP         | R/W | Ah      | Effektive Gesamtkapazität           |
| 0x0016        | LBP         | R/W | %       | Low Battery Alarm Schwellwert       |
| 0x0017        | LVP         | R/W | V       | Unterspannungsschutz                |
| 0x0018        | OVP         | R/W | V       | Überspannungsschutz                 |
| 0x001A        | OCP         | R/W | A       | Überstromschutz                     |

**Konfigurationsregister (per Modbus beim Start setzen):**

| Adresse | Name  | Wert | Beschreibung                    |
|---------|-------|------|---------------------------------|
| LIGHT   | -     | 0    | Display auf dunkelst (Strom sparen) |
| BEP     | -     | OFF  | Buzzer deaktivieren             |
| ADD     | -     | 1    | Modbus Adresse (Default)        |
| BAUD    | -     | 115200 | Baudrate (Default)            |

### Alarmcodes

| Code | Beschreibung | Priorität |
|------|--------------|-----------|
| OCP  | Überstrom    | Höchste   |
| NBE  | Kein Akku    | 2         |
| NCH  | Kein Ladegerät | 3       |
| OVP  | Überspannung | 10        |
| LVP  | Unterspannung | 11       |
| CAP  | Kapazitätsschwelle | 14  |

### ROS2 Topics (Cortex → Pi)

```
/r2d2/battery/state    (sensor_msgs/BatteryState)  1 Hz
  → voltage, current, charge, percentage, temperature

/r2d2/battery/alert    (std_msgs/String)
  → "low_battery"      (SOC < 20%)
  → "critical"         (SOC < 10%)
  → "charging"         (Ladegerät verbunden)
  → "charging_complete"
  → "alarm:<CODE>"     (OCP, LVP, OVP etc.)
```

### Low Battery Flow

```
SOC < 20%  → /r2d2/battery/alert: "low_battery"
           → RGB Matrix: Violett blinken
           → Pi: Navigation zur Ladestation einleiten

SOC < 10%  → /r2d2/battery/alert: "critical"
           → Forced Shutdown Sequenz

Andocken   → Ladegerät erkannt (VCHARGE > 0)
           → Modbus: MODE = 2 (UPS)
           → RGB Matrix: Violett sweep
           → Roboter läuft weiter ohne Unterbrechung
```

### Kapazitätskalibrierung (Erstinbetriebnahme)

Beim ersten Einsatz oder Akkutausch muss die Gesamtkapazität gesetzt werden.
Entweder manuell über die Tasten (CAP SET) oder per Modbus (Register 0x0015).
Nach vollständiger Entladung und anschließendem vollem Laden kalibriert das
Gerät die Kapazität automatisch (Learning Mode).

---

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
| Charging | Violett | Langsamer Sweep | Am Ladekabel (UPS Mode) |
| Low Battery | Violett | Blinken | SOC < 20% |
| Shutdown | Rot | Fade out | System fährt herunter |

---

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

---

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

---

## Wake aus Deep Idle: Mechanismen

| Mechanismus | Unterstützt | Details |
|---|---|---|
| Physischer Knopf | ✅ | GPIO an Cortex, interrupt-driven |
| Timer (täglich/geplant) | ✅ | ESP32 RTC oder Software-Timer |
| Wake Word (Stimme) | ❌ | ReSpeaker braucht Pi – nicht möglich in Deep Idle |

Voice Wake ist in allen anderen States verfügbar (Voice-only idle, Navigation
idle, Full active). Deep Idle ist nur für "wirklich aus" — manuelle oder
geplante Aktivierung.

---

## Warum Cortex und nicht Head ESP32?

Die 8x8 RGB Matrix war ursprünglich für den Head ESP32 geplant.
Sie sitzt am Cortex weil:

- **Immer sichtbar**: Status auch wenn Pi aus ist (Deep Idle)
- **Unabhängig**: kein ROS2 nötig für Basis-Status
- **Sicherheit**: Fehler und Shutdown-Status immer anzeigbar
- **Einfacher**: Head ESP32 wird schlanker

Der Head ESP32 behält SerLCD 40x2 für Text-Output und Ultraschall-Sensor.
