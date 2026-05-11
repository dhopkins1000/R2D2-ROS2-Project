# XY-BT13L – Complete Modbus Register Map

Derived from live register scan (register_scan firmware, 2026-05).
All 32 responding registers (0x0000–0x001F) documented.
Registers 0x0020 and above return no response — this is the complete register space.

## Communication Parameters

| Parameter    | Value                        |
|--------------|------------------------------|
| Interface    | TTL UART (3.3V logic — confirmed with multimeter) |
| Baud Rate    | 115200 (default)             |
| Format       | 8N1 (no parity, 1 stop bit)  |
| Slave Address| 1 (default)                  |
| Function Codes | 0x03 (read), 0x06 (write single), 0x10 (write multiple) |

No RS485 adapter needed — connect XY-BT13L TX/RX directly to ESP32 UART pins.

## Wiring (Cortex ESP32 LOLIN D32)

```
XY-BT13L TX  →  GPIO16 (UART2 RX)
XY-BT13L RX  ←  GPIO17 (UART2 TX)
XY-BT13L GND —  GND
XY-BT13L 5V  ✗  DO NOT connect
```

---

## Complete Register Table

### Read-Only Registers — Live Data

| Address | Name        | Unit  | Divisor | Example Raw | Interpreted  | Notes                                      |
|---------|-------------|-------|---------|-------------|--------------|--------------------------------------------|
| 0x0000  | MODE        | —     | —       | 2           | 1=Discharge  | R/W. 0=Charge, 1=Discharge, 2=UPS         |
| 0x0001  | CH_RELAY    | —     | —       | 0           | OFF          | Charging relay status                      |
| 0x0002  | DCH_RELAY   | —     | —       | 1           | ON           | Discharging relay status                   |
| 0x0003  | AH_LOW      | Ah    | ÷100    | 1174        | 11.74 Ah     | Remaining capacity, lower 16 bits          |
| 0x0004  | AH_HIGH     | Ah    | ÷100    | 0           | —            | Remaining capacity, upper 16 bits          |
| 0x0005  | WH_LOW      | Wh    | ÷100    | 15415       | 154.15 Wh    | Remaining energy, lower 16 bits            |
| 0x0006  | WH_HIGH     | Wh    | ÷100    | 0           | —            | Remaining energy, upper 16 bits            |
| 0x0007  | PER         | %     | ÷10     | 495         | 49.5%        | State of Charge                            |
| 0x0008  | VCHARGE     | V     | ÷100    | 55          | 0.55V        | Charger voltage. Use >1.0V as threshold for charger detection (noise ~0.5V when no charger) |
| 0x0009  | VBAT        | V     | ÷100    | 1313        | 13.13V       | Battery voltage                            |
| 0x000A  | IBAT        | A     | ÷100    | 16          | 0.16A        | Battery current                            |
| 0x000B  | W_LOW       | mW    | ÷1000   | 2096        | 2.096W       | Instantaneous power, lower 16 bits. Verified: matches VBAT×IBAT |
| 0x000C  | W_HIGH      | mW    | ÷1000   | 0           | —            | Instantaneous power, upper 16 bits         |
| 0x000D  | CH_Runtime  | min   | —       | 0           | 0 min        | Charging session runtime                   |
| 0x000E  | DCH_Runtime | min   | —       | 6           | 6 min        | Discharging session runtime (increments live) |
| 0x000F  | LOOPCOUNT   | —     | —       | 0           | 0 cycles     | Completed charge/discharge cycles          |
| 0x0010  | IN_TEMP     | °C    | ÷10     | 262         | 26.2°C       | Module board temperature (rises with use)  |
| 0x0011  | EX_TEMP     | °C    | ÷10     | 0           | No sensor    | External NTC probe temperature             |
| 0x0012  | ALARM       | —     | —       | 2           | NBE          | See alarm table below. R/W                 |
| 0x0013  | STOP        | —     | —       | 0           | Running       | Mode pause flag. R/W                       |
| 0x0014  | LEARN       | —     | —       | 0           | Off          | Learning/calibration mode. R/W             |

### Read/Write Registers — Configuration

| Address | Name   | Unit | Divisor | Scan Value | Interpreted  | Correct for 12V Lead-Acid | Notes                              |
|---------|--------|------|---------|------------|--------------|---------------------------|------------------------------------||
| 0x0015  | CAP    | Ah   | —       | 24         | 24 Ah        | Set to actual Ah capacity | Raw value IS Ah, no divisor        |
| 0x0016  | LBP    | %    | —       | 0          | Disabled     | 20 (alert at 20% SOC)    | Low battery protection threshold   |
| 0x0017  | LVP    | V    | ÷100    | 100        | **1.00V ⚠️** | 1150 (11.50V)            | **MUST configure before use!** 1V is dangerously low for any 12V battery |
| 0x0018  | OVP    | V    | ÷100    | 0          | **Disabled ⚠️**| 1500 (15.00V)           | **MUST configure before use!**     |
| 0x0019  | LAP    | A    | ÷100    | 0          | Disabled     | Leave disabled            | Low current threshold              |
| 0x001A  | OCP    | A    | ÷100    | 3000       | 30.00A ✓     | 3000 (30A)               | Max current — correct for BT13L   |

### Unknown Registers (discovered in scan)

| Address | Raw Value | Best Guess                  | Notes                                                        |
|---------|-----------|-----------------------------|--------------------------------------------------------------|
| 0x001B  | 0         | FOP or LOP threshold        | Forced conduction time or cycle count threshold              |
| 0x001C  | 110       | OHP (runtime limit, minutes)| 110 minutes runtime protection. Matches OHP parameter in manual |
| 0x001D  | 0         | Unknown config              |                                                              |
| 0x001E  | 0         | Unknown config              |                                                              |
| 0x001F  | 0         | Unknown config              |                                                              |

---

## Alarm Codes (Register 0x0012)

| Code | Name | Description                  | Action in Firmware                        |
|------|------|------------------------------|-------------------------------------------|
| 0    | OK   | No alarm                     | Normal                                    |
| 1    | OCP  | Overcurrent                  | ALERT — publish to /r2d2/battery/alert    |
| 2    | NBE  | No battery detected          | Expected with lab PSU. With real battery, treat as ALERT |
| 3    | NCH  | No charger connected         | **Normal operating state** — ignore       |
| 4    | REV  | Reverse current              | ALERT                                     |
| 5    | VOE  | Voltage anomaly              | ALERT                                     |
| 6    | OTP  | Overtemperature (board)      | ALERT                                     |
| 7    | ETP  | Overtemperature (external)   | ALERT                                     |
| 8    | LOP  | Cycle count threshold        | ALERT                                     |
| 9    | HFC  | Relay high-frequency alarm   | ALERT                                     |
| 10   | OVP  | Overvoltage                  | ALERT                                     |
| 11   | LVP  | Undervoltage                 | ALERT                                     |
| 12   | LAP  | Low current                  | ALERT                                     |
| 13   | OHP  | Runtime threshold            | ALERT                                     |
| 14   | CAP  | Capacity threshold           | ALERT                                     |

---

## Scaling Summary

```
VBAT     = raw / 100.0   [V]
IBAT     = raw / 100.0   [A]
VCHARGE  = raw / 100.0   [V]  — charger connected if > 1.0V
PER/SOC  = raw / 10.0    [%]
IN_TEMP  = raw / 10.0    [°C]
EX_TEMP  = raw / 10.0    [°C]
AH       = (AH_HIGH<<16 | AH_LOW) / 100.0  [Ah]
WH       = (WH_HIGH<<16 | WH_LOW) / 100.0  [Wh]
W_INST   = (W_HIGH<<16  | W_LOW)  / 1000.0 [W]
CAP      = raw           [Ah]  (no divisor)
LVP      = raw / 100.0   [V]
OVP      = raw / 100.0   [V]
OCP      = raw / 100.0   [A]
```

---

## ⚠️ Required Configuration Before Real Battery Use

The following registers are **unconfigured or dangerously wrong** from the factory scan.
Set these via Modbus (FC 0x06) or manually via the module buttons before connecting a real battery:

| Register | Parameter | Current (raw) | Required for 12V Lead-Acid | Required for 3S Li-Ion |
|----------|-----------|---------------|----------------------------|------------------------|
| 0x0015   | CAP       | 24            | Actual Ah of your battery  | Actual Ah of your battery |
| 0x0016   | LBP       | 0 (disabled)  | 20 (alert at 20% SOC)      | 20                     |
| 0x0017   | LVP       | 100 = 1.00V ⚠️ | 1150 = 11.50V             | 1000 = 10.00V (3S)     |
| 0x0018   | OVP       | 0 (disabled) ⚠️| 1500 = 15.00V             | 1260 = 12.60V (3S)     |

---

## Charger Detection Logic

Do not rely on ALARM code for charger detection. Use VCHARGE:

```cpp
bool chargerConnected = (vcharge_raw > 100);  // > 1.00V = charger present
// raw 55-58 is noise when no charger (~0.55V) — safely below threshold
```

---

## MODE Register Usage

| Value | Mode       | Relay State                    | Use Case                         |
|-------|------------|--------------------------------|----------------------------------|
| 0     | Charge     | CH_RELAY=ON, DCH=OFF           | Charging only                    |
| 1     | Discharge  | CH_RELAY=OFF, DCH=ON           | Normal operation                 |
| 2     | UPS        | Both ON                        | Docked at charging station — robot continues running while charging |

Write via FC 0x06: address=0x0000, value=0/1/2
