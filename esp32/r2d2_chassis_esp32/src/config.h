#pragma once

// ============================================================
// R2D2 Chassis ESP32 – Konfiguration
// Alle Pins, Topics und Parameter zentral hier definieren.
// Änderungen hier → nur neu flashen, kein Code-Umbau nötig.
// ============================================================

// --- micro-ROS Node ---
#define NODE_NAME        "r2d2_chassis"
#define NODE_NAMESPACE   ""

// --- ROS2 Topics ---
#define TOPIC_STATUS     "/r2d2/chassis/status"       // std_msgs/String  (heartbeat)
#define TOPIC_CMD_VEL    "/r2d2/chassis/cmd_vel"      // geometry_msgs/Twist (später)
#define TOPIC_ODOM       "/r2d2/chassis/odom"         // nav_msgs/Odometry   (später)
#define TOPIC_COMPASS    "/r2d2/chassis/compass"      // std_msgs/Float32    (später)
#define TOPIC_STAIR      "/r2d2/chassis/stair_alert"  // std_msgs/Bool       (später)

// --- MD25 Motor Controller (UART) ---
#define MD25_UART        Serial2
#define MD25_BAUD        9600
#define MD25_TX_PIN      17    // ESP32 TX2 → MD25 RX
#define MD25_RX_PIN      16    // ESP32 RX2 ← MD25 TX

// --- I2C Bus 0 (HMC5883L Kompass + Ultrasonic Stair Sensor) ---
#define I2C0_SDA_PIN     21
#define I2C0_SCL_PIN     22

// --- HMC5883L Kompass ---
#define HMC5883L_ADDR    0x1E

// --- Ultrasonic Stair Sensor SRF02 (I2C) ---
#define ULTRASONIC_ADDR  0x71

// --- SSD1306 OLED (SPI) ---
#define OLED_CLK_PIN     18    // SPI CLK
#define OLED_MOSI_PIN    23    // SPI MOSI
#define OLED_CS_PIN       5    // Chip Select
#define OLED_DC_PIN       4    // Data/Command
#define OLED_RST_PIN     26    // Reset

// --- Timing ---
#define HEARTBEAT_MS     1000  // Status-Topic publish interval
#define SPIN_TIMEOUT_MS   100  // micro-ROS executor spin timeout
