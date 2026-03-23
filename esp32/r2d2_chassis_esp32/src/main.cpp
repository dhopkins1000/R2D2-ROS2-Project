#include <Arduino.h>
#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/string.h>

#include "config.h"

// --- micro-ROS Objekte ---
rcl_node_t node;
rcl_publisher_t pub_status;
std_msgs__msg__String msg_status;
rclc_executor_t executor;
rclc_support_t support;
rcl_allocator_t allocator;

// --- Fehlerbehandlung ---
// Bei hartem Fehler: schnelles LED-Blinken + Stopp
#define RCCHECK(fn) { \
  rcl_ret_t rc = fn; \
  if (rc != RCL_RET_OK) { error_loop(__LINE__); } \
}
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop(int line) {
  Serial.printf("[ERROR] micro-ROS init fehlgeschlagen (line %d)\n", line);
  while (1) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    delay(100);
  }
}

// --- Setup ---
void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("[R2D2 Chassis] Booting...");

  // micro-ROS Serial Transport (USB → Pi micro-ROS Agent)
  set_microros_serial_transports(Serial);
  delay(2000);  // Agent-Verbindung abwarten

  allocator = rcl_get_default_allocator();

  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, NODE_NAME, NODE_NAMESPACE, &support));

  // Publisher: Heartbeat/Status
  RCCHECK(rclc_publisher_init_default(
    &pub_status,
    &node,
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
    TOPIC_STATUS
  ));

  RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));

  // Message-Buffer allozieren
  msg_status.data.data     = (char*)malloc(64 * sizeof(char));
  msg_status.data.capacity = 64;
  msg_status.data.size     = 0;

  Serial.println("[R2D2 Chassis] micro-ROS bereit.");
  Serial.printf("  Node:  %s\n", NODE_NAME);
  Serial.printf("  Topic: %s\n", TOPIC_STATUS);

  // TODO: MD25 UART init (MD25_UART.begin(MD25_BAUD, SERIAL_8N1, MD25_RX_PIN, MD25_TX_PIN))
  // TODO: Wire.begin(I2C0_SDA_PIN, I2C0_SCL_PIN) für HMC5883L + Ultrasonic
  // TODO: SSD1306 SPI init
}

// --- Loop ---
void loop() {
  static unsigned long last_publish = 0;
  unsigned long now = millis();

  // Heartbeat-Status publishen
  if (now - last_publish >= HEARTBEAT_MS) {
    last_publish = now;

    snprintf(msg_status.data.data, msg_status.data.capacity,
             "R2D2 Chassis Online | uptime: %lus", now / 1000);
    msg_status.data.size = strlen(msg_status.data.data);

    RCSOFTCHECK(rcl_publish(&pub_status, &msg_status, NULL));
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));  // Heartbeat LED
  }

  rclc_executor_spin_some(&executor, RCL_MS_TO_NS(SPIN_TIMEOUT_MS));
}
