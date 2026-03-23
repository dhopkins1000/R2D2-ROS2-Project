#include <Arduino.h>
#include <micro_ros_arduino.h>
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

bool microros_initialized = false;

// --- Fehlerbehandlung ---
#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) return false; }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

// --- micro-ROS initialisieren (retry-fähig) ---
bool microros_init() {
  allocator = rcl_get_default_allocator();

  if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
  if (rclc_node_init_default(&node, NODE_NAME, NODE_NAMESPACE, &support) != RCL_RET_OK) return false;

  RCCHECK(rclc_publisher_init_default(
    &pub_status,
    &node,
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
    TOPIC_STATUS
  ));

  RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));

  if (!msg_status.data.data) {
    msg_status.data.data     = (char*)malloc(64 * sizeof(char));
    msg_status.data.capacity = 64;
    msg_status.data.size     = 0;
  }

  return true;
}

// --- micro-ROS aufräumen vor Retry ---
void microros_cleanup() {
  rcl_publisher_fini(&pub_status, &node);
  rcl_node_fini(&node);
  rclc_support_fini(&support);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("[R2D2 Chassis] Booting...");

  set_microros_transports();

  // TODO: MD25 UART init
  // TODO: Wire.begin(I2C0_SDA_PIN, I2C0_SCL_PIN)
  // TODO: SSD1306 SPI init
}

void loop() {
  // --- Reconnect-Loop: versucht Agent zu erreichen bis es klappt ---
  if (!microros_initialized) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));  // Langsames Blinken = warte auf Agent
    delay(500);

    Serial.println("[R2D2 Chassis] Warte auf micro-ROS Agent...");

    if (microros_init()) {
      microros_initialized = true;
      digitalWrite(LED_BUILTIN, HIGH);
      Serial.println("[R2D2 Chassis] micro-ROS verbunden!");
      Serial.printf("  Node:  %s\n", NODE_NAME);
      Serial.printf("  Topic: %s\n", TOPIC_STATUS);
    }
    return;
  }

  // --- Normaler Betrieb ---
  static unsigned long last_publish = 0;
  unsigned long now = millis();

  if (now - last_publish >= HEARTBEAT_MS) {
    last_publish = now;

    snprintf(msg_status.data.data, msg_status.data.capacity,
             "R2D2 Chassis Online | uptime: %lus", now / 1000);
    msg_status.data.size = strlen(msg_status.data.data);

    if (rcl_publish(&pub_status, &msg_status, NULL) != RCL_RET_OK) {
      // Verbindung verloren – neu verbinden
      Serial.println("[R2D2 Chassis] Verbindung verloren, reconnect...");
      microros_cleanup();
      microros_initialized = false;
      return;
    }

    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));  // Heartbeat LED
  }

  rclc_executor_spin_some(&executor, RCL_MS_TO_NS(SPIN_TIMEOUT_MS));
}
