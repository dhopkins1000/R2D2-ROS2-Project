#pragma once

// ============================================================
// R2D2 Head ESP32 – Konfiguration
// Alle Pins, Topics und Parameter zentral hier definieren.
// ============================================================

// --- micro-ROS Node ---
#define NODE_NAME        "r2d2_head"
#define NODE_NAMESPACE   ""

// --- ROS2 Topics ---
#define TOPIC_STATUS     "/r2d2/head/status"        // std_msgs/String  (heartbeat)
#define TOPIC_HEAD_CMD   "/r2d2/head/cmd"           // std_msgs/Float32 (subscriber, Zielwinkel in Grad)
#define TOPIC_HEAD_POS   "/r2d2/head/position"      // std_msgs/Float32 (aktueller Winkel in Grad)
#define TOPIC_DISTANCE   "/r2d2/head/distance"      // sensor_msgs/Range (Ultraschall vorne)

// --- A4988 Schrittmotor (Kopfrotation) ---
#define STEPPER_STEP_PIN  17    // STEP Signal
#define STEPPER_DIR_PIN   16    // DIR Signal
#define STEPPER_EN_PIN     4    // ENABLE (LOW = aktiv)
#define STEPPER_STEPS_PER_REV 200   // Schritte pro Umdrehung (1/1 Step)
#define STEPPER_MICROSTEPS    8     // Microstepping-Faktor (je nach MS1/MS2/MS3 Jumper)
#define STEPPER_SPEED_RPM    10     // Zielgeschwindigkeit

// --- SerLCD 40x2 Display (UART) ---
// SerLCD kommuniziert über UART mit 9600 Baud
// Benötigt Logic Level Converter (5V↔3.3V)
#define SERLCD_UART      Serial2
#define SERLCD_BAUD      9600
#define SERLCD_TX_PIN    21    // ESP32 TX → SerLCD RX
#define SERLCD_RX_PIN    22    // nicht belegt (SerLCD sendet nicht)

// --- I2C Ultraschall Sensor (vorne, Abstandsmessung) ---
// Modell noch zu ermitteln – Placeholder
#define I2C_SDA_PIN      21    // TODO: andere Pins wenn SerLCD UART auf 21/22 liegt
#define I2C_SCL_PIN      22    // TODO: konfliktfrei mit SerLCD planen
#define ULTRASONIC_ADDR  0x70  // Placeholder – echte Adresse nach I2C Scan

// --- Timing ---
#define HEARTBEAT_MS     1000  // Status-Topic publish interval
#define SPIN_TIMEOUT_MS   100  // micro-ROS executor spin timeout
