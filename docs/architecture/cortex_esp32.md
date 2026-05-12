# Cortex ESP32 – Power Controller & Status Indicator

## Konzept

Ein dedizierter ESP32 der **immer aktiv** ist (~0.05W) und drei Aufgaben hat:
1. **Power Management** – steuert alle Stromkreise via DS2413 + MOSFETs
2. **Battery Monitoring** – liest XY-BT13L via UART (Modbus RTU)
3. **Visual Status Indicator** – zeigt R2D2's Zustand über RGB Matrix

## Hardware

```
Cortex ESP32 (LOLIN D32)
  ├── HT16K33 8x8 RGB Matrix  (I2C, GPIO21/22, Adresse 0x72) ← Status Indicator
  ├── DS2413 #1               (1-Wire)                        ← Dual Power Switch
  │     ├── Channel A → IRLZ44N N-FET                        ← 12V MD25 GND-side
  │     └── Channel B → IRF4905 P-FET                        ← 5V Pi VCC-side
  ├── XY-BT13L Battery Manager (UART2, GPIO16=RX, GPIO17=TX)  ← Battery Monitoring
  └── Wake Button              (GPIO35, input-only)           ← Wake from deep idle
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

## Commissioning Findings (Live-Inbetriebnahme)

Erfahrungen aus der ersten Inbetriebnahme — wichtig für zukünftige Setups:

### HT16K33 I2C Adresse: 0x72 (nicht 0x70)
Das Modul antwortet auf **0x72**, nicht auf die Standardadresse 0x70.
Immer einen I2C-Scan durchführen bevor die Adresse im Code hartkodiert wird:
```cpp
Wire.begin(21, 22);
for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0)
        Serial.printf("I2C device at 0x%02X\n", addr);
}
```

### XY-BT13L Modbus Baudrate: 115200
Die Werkseinstellung des XY-BT13L ist **115200 Baud** — nicht 9600.
`Serial2.begin()` muss explizit mit Baudrate und Pins initialisiert werden:
```cpp
// Korrekt:
Serial2.begin(115200, SERIAL_8N1, 16, 17);
_node.begin(1, Serial2);

// Falsch (Default 9600, keine expliziten Pins):
Serial2.begin(9600);
```

### ModbusMaster: Serial2 direkt verwenden
`HardwareSerial _serial(2)` als Wrapper funktioniert nicht zuverlässig.
`Serial2` direkt an ModbusMaster übergeben:
```cpp
ModbusMaster _node;
_node.begin(1, Serial2);  // ✓ funktioniert
```

### Brownout bei WiFi-Initialisierung
WiFi-Init zieht kurz 300–500mA — zu viel für schwache USB-Hubs oder
USB-Anschlüsse am Pi. Lösung: Brownout-Detektor in setup() deaktivieren
und powered USB-Hub verwenden:
```cpp
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);  // ganz am Anfang von setup()
```

### Powered USB Hub erforderlich
Unpowered USB Hub → Brownout → Bootloop → auch XY-BT13L Modbus Fehler.
Der Hub muss ein eigenes Netzteil haben wenn ESP32 + weitere Geräte daran hängen.

---

## Battery Management (XY-BT13L)

### Hardware

Das XY-BT13L ist ein 30A Battery Management Modul (10–110V) mit integriertem
Coulomb Counter, Lade-/Entladerelais, OVP/LVP/OCP/OTP Schutz und einem
**TTL-seriellen Modbus RTU Interface**.

**Kein RS485-Adapter nötig** — das Modul spricht direkt TTL UART.
TX-Pin des Moduls liefert **3,3V Logikpegel** (gemessen), direkt kompatibel
mit dem ESP32. Kein Levelshifter erforderlich.

```
Cortex ESP32 (LOLIN D32)        XY-BT13L
  GPIO17 (UART2 TX) ──────────→ RX
  GPIO16 (UART2 RX) ←────────── TX  (3.3V bestätigt ✓)
  GND               ──────────── GND
  —                 ✗            5V  (nicht verbinden — Modulversorgung intern)
```

**Modbus Parameter (Werkseinstellung):**
- Baud Rate: **115200** (nicht 9600!)
- Format: 8N1 (kein Parity, 1 Stop Bit)
- Slave Adresse: 1

### Wiring — Strompfad

```
Akku       (BT+/BT-)  ──→ XY-BT13L ──→ System (OUT+/OUT-)
Ladegerät  (IN+/IN-)  ──→ XY-BT13L
```

Das XY-BT13L sitzt als Gateway zwischen Akku, Ladegerät und Last.
Es verwaltet Lade- und Entladerelais eigenständig nach konfigurierten
Schwellwerten.

### ⚠️ Relay-Blocking durch aktive Alarme

**Bestätigt durch Live-Test:** Jeder aktive Alarm (inkl. NBE) verhindert
das Schließen des DCH-Relais, selbst wenn MODE=DCHG gesetzt ist.
OUT+/OUT- hat erst Spannung nach Alarm-Quittierung.

Alarm quittieren per Modbus: `writeSingleRegister(0x0012, 0)`

**Firmware-Startup-Sequenz:**
```
1. Boot → ALARM Register (0x0012) lesen
2. Falls ALARM != 0 und != 3 (NCH): per Modbus auf 0 setzen, 200ms warten
3. MODE = 1 (DCHG) schreiben → Register 0x0000
4. 200ms warten, DCH_RELAY (0x0002) == 1 verifizieren
5. Monitoring-Loop starten
```

### NCH — Normaler Betriebszustand ohne Ladegerät

Im Normalbetrieb zeigt das Modul dauerhaft **NCH** (No Charger).
Das ist kein Fehler — wird in der Firmware ignoriert.

Charger-Erkennung über VCHARGE (Register 0x0008):
```
VCHARGE = 0   →  Normalbetrieb (NCH ignorieren)
VCHARGE > 1V  →  Ladegerät verbunden → UPS Mode aktivieren
```
Noise-Schwellwert: raw > 100 (entspricht 1.00V) als Charger-Erkennung.
Rohwert 55–58 ist Rauschen ohne Ladegerät (~0.55V).

### UPS Mode — Laden während Betrieb

Im UPS-Modus sind beide Relais gleichzeitig geschlossen.
Das Ladegerät versorgt die Last **und** lädt den Akku parallel.

**Für R2D2 ideal:** Während des Dockens läuft der Roboter weiter.
UPS Mode wird beim Andocken per Modbus aktiviert (Register 0x0000 = 2).

**Einschränkung:** MODE-Write wird im UPS-Modus ignoriert.
Zum Beenden muss das Ladegerät physisch getrennt werden.

### Relay-Verhalten nach Mode

| MODE | Name       | CH_RELAY | DCH_RELAY | OUT Spannung | Verwendung              |
|------|------------|----------|-----------|--------------|-------------------------|
| 0    | Charge     | ON       | OFF       | Keine        | Nur Laden, kein Betrieb |
| 1    | Discharge  | OFF      | ON        | ✅ Akku-V    | Normalbetrieb R2D2      |
| 2    | UPS        | ON       | ON        | ✅ Akku-V    | Docking + Laden         |

### Modbus Registersatz

| Adresse | Name        | R/W | Einheit | Divisor | Beschreibung                    |
|---------|-------------|-----|---------|---------|---------------------------------|
| 0x0000  | MODE        | R/W | —       | —       | 0=Charge, 1=Discharge, 2=UPS    |
| 0x0001  | CH_RELAY    | R   | —       | —       | Laderelais Status               |
| 0x0002  | DCH_RELAY   | R   | —       | —       | Entladerelais Status            |
| 0x0003  | AH_LOW      | R   | Ah      | ÷100    | Kapazität rest. (low 16 bit)    |
| 0x0004  | AH_HIGH     | R   | Ah      | ÷100    | Kapazität rest. (high 16 bit)   |
| 0x0005  | WH_LOW      | R   | Wh      | ÷100    | Energie rest. (low 16 bit)      |
| 0x0006  | WH_HIGH     | R   | Wh      | ÷100    | Energie rest. (high 16 bit)     |
| 0x0007  | PER         | R   | %       | ÷10     | State of Charge (SOC)           |
| 0x0008  | VCHARGE     | R   | V       | ÷100    | Ladegerät-Spannung              |
| 0x0009  | VBAT        | R   | V       | ÷100    | Batteriespannung                |
| 0x000A  | IBAT        | R   | A       | ÷100    | Batteriestrom                   |
| 0x000B  | W_LOW       | R   | mW      | ÷1000   | Leistung (low 16 bit)           |
| 0x000C  | W_HIGH      | R   | mW      | ÷1000   | Leistung (high 16 bit)          |
| 0x000D  | CH_Runtime  | R   | Min     | —       | Laufzeit Laden                  |
| 0x000E  | DCH_Runtime | R   | Min     | —       | Laufzeit Entladen               |
| 0x000F  | LOOPCOUNT   | R   | —       | —       | Anzahl Ladezyklen               |
| 0x0010  | IN_TEMP     | R   | °C      | ÷10     | Boardtemperatur                 |
| 0x0011  | EX_TEMP     | R   | °C      | ÷10     | Externe Temperatur (NTC Probe)  |
| 0x0012  | ALARM       | R/W | —       | —       | Alarmstatus (0 = quittieren)    |
| 0x0015  | CAP         | R/W | Ah      | —       | Effektive Gesamtkapazität       |
| 0x0016  | LBP         | R/W | %       | —       | Low Battery Alarm Schwellwert   |
| 0x0017  | LVP         | R/W | V       | ÷100    | Unterspannungsschutz ⚠️         |
| 0x0018  | OVP         | R/W | V       | ÷100    | Überspannungsschutz ⚠️          |
| 0x001A  | OCP         | R/W | A       | ÷100    | Überstromschutz                 |

**⚠️ Konfiguration vor echtem Akkueinsatz:**

| Register | Parameter | Werk (raw) | 12V Blei-Acid | 3S Li-Ion  |
|----------|-----------|------------|---------------|------------|
| 0x0017   | LVP       | 100=1.00V  | 1150=11.50V   | 1000=10.00V|
| 0x0018   | OVP       | 0=disabled | 1500=15.00V   | 1260=12.60V|
| 0x0016   | LBP       | 0=disabled | 20 (%)        | 20 (%)     |
| 0x0015   | CAP       | 24 Ah      | Actual Ah     | Actual Ah  |

### Alarmcodes

| Code | Name | Relay-Verhalten    | Firmware-Aktion               |
|------|------|--------------------|-------------------------------|
| 0    | OK   | Normal             | Normal                        |
| 1    | OCP  | Relay öffnet       | ALERT + quittieren            |
| 2    | NBE  | **Relay blockiert**| Mit PSU normal; mit Akku ALERT|
| 3    | NCH  | Normal             | **Ignorieren — Normalzustand**|
| 5    | VOE  | Relay öffnet       | ALERT + DCHG re-assertieren   |
| 10   | OVP  | Relay öffnet       | ALERT + quittieren            |
| 11   | LVP  | Relay öffnet       | ALERT + quittieren            |

### ROS2 Topics (Cortex → Pi)

```
/r2d2/battery/state    (sensor_msgs/BatteryState)  1 Hz
/r2d2/battery/alert    (std_msgs/String)
  → "low_battery"      (SOC < 20%)
  → "critical"         (SOC < 10%)
  → "charging"         (VCHARGE > 1.0V erkannt)
  → "alarm:<CODE>"     (NCH wird NICHT weitergeleitet)
```

### Low Battery Flow

```
SOC < 20%    → alert: "low_battery" + RGB: Violett blinken
SOC < 10%    → alert: "critical"    + Forced Shutdown
VCHARGE > 1V → MODE=UPS + RGB: Violett sweep + alert: "charging"
VCHARGE = 0  → MODE=DCHG + RGB: vorheriger State
```

---

## RGB Matrix – Status Zustände

| Zustand     | Farbe       | Animation              |
|-------------|-------------|------------------------|
| Boot        | Weiß        | Wipe links → rechts    |
| Active      | Blau        | Langsam pulsieren      |
| Standalone  | Gelb        | Langsam pulsieren      |
| Navigating  | Grün        | Rotation / Sweep       |
| Listening   | Cyan        | Schnelles Pulsieren    |
| Speaking    | Gelb        | Wellen-Animation       |
| Idle        | Orange      | Sehr langsames Glimmen |
| Deep Idle   | Orange      | Einzelne Pixel, langsam|
| Error       | Rot         | Blinken                |
| Charging    | Violett     | Langsamer Sweep        |
| Low Battery | Violett     | Blinken                |
| Health AP   | Cyan        | Langsam pulsieren      |
| Shutdown    | Rot         | Fade out               |

HT16K33 I2C Adresse: **0x72** (bestätigt, nicht Default 0x70)

---

## WiFi & HTTP Health Server

```
STA Mode (normal):  verbindet mit Heimnetz, HTTP auf lokaler IP
AP Mode (auf Knopf): SSID "R2D2-Status", PW "r2d2health", IP 192.168.4.1
```

**AP aktivieren:** Langer Tastendruck (>3s) auf GPIO35 ODER Pi ist aus.
**Health Page:** `http://<IP>/` — zeigt VBAT, SOC, IBAT, TEMP, Mode, Status
**JSON API:** `http://<IP>/status`
**Wake Button:** POST `/wake` auf der Health Page

---

## ROS2 Topic Interface

```
/r2d2/power/state   (std_msgs/String) → vom Pi empfangen
  "active" / "navigating" / "listening" / "speaking"
  "idle" / "shutdown" / "error" / "charging"

/r2d2/cortex/leds   (std_msgs/String, JSON) → direkte LED-Steuerung
```

---

## Power Management

### DS2413 Firmware

```cpp
// DS2413 open-drain LOW = MOSFET ON (invertierte Logik)
void setPower(bool md25, bool pi) {
    ds2413.setOutput(!md25, !pi);
}
```

### Shutdown Sequenz
```
Pi → /r2d2/power/state: "shutdown"
Cortex → Rot fade-out
Cortex → GPIO32 LOW (500ms) → Pi initiiert shutdown
Cortex → wartet auf GPIO34 LOW (Pi shutdown complete) oder Timeout 15s
Cortex → DS2413: Pi OFF, MD25 OFF
Cortex → State: DEEP_IDLE (Orange Animation)
```

### Wake Sequenz
```
Trigger: GPIO35 Knopf ODER POST /wake auf Health Page
Cortex → Weiß wipe Animation
Cortex → DS2413: Pi ON
Cortex → wartet auf micro-ROS Agent
Pi → /r2d2/power/state: "active"
Cortex → State: ACTIVE (Blau pulsieren)
```

### Watchdog
```
Kein /r2d2/power/state Heartbeat für >30s → Rot blinken
Kein Heartbeat für >60s → Hard Power Cycle (DS2413: Pi OFF → 5s → Pi ON)
```

---

## Wake-Mechanismen aus Deep Idle

| Mechanismus        | Status | Details                                   |
|--------------------|--------|-------------------------------------------|
| Physischer Knopf   | ✅     | GPIO35, interrupt-driven                  |
| HTTP /wake Button  | ✅     | WiFi AP muss aktiv sein                   |
| Timer (geplant)    | ✅     | ESP32 RTC                                 |
| Wake Word (Stimme) | ❌     | ReSpeaker braucht Pi — nicht möglich      |
