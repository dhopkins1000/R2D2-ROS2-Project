#include <Arduino.h>
#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/string.h>

// micro-ROS Objekte
rcl_node_t node;
rcl_publisher_t publisher;
std_msgs__msg__String msg;
rclc_executor_t executor;
rclc_support_t support;
rcl_allocator_t allocator;

// Fehlerbehandlung
#define RCCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){error_loop();}}
#define RCSOFTCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){;}}

void error_loop() {
  // Bei Fehler: LED blinkt schnell
  while(1) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    delay(100);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);

  // micro-ROS Serial Transport initialisieren
  set_microros_serial_transports(Serial);
  delay(2000);  // Warten bis Agent verbunden

  allocator = rcl_get_default_allocator();

  // ROS2 Node initialisieren
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, "r2d2_chassis", "", &support));

  // Publisher: /r2d2/chassis/status
  RCCHECK(rclc_publisher_init_default(
    &publisher,
    &node,
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
    "/r2d2/chassis/status"
  ));

  // Executor
  RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));

  // Nachricht initialisieren
  msg.data.data = (char*)malloc(50 * sizeof(char));
  msg.data.capacity = 50;
  msg.data.size = 0;
}

void loop() {
  // Status publishen
  snprintf(msg.data.data, msg.data.capacity, "R2D2 Chassis Online");
  msg.data.size = strlen(msg.data.data);

  RCSOFTCHECK(rcl_publish(&publisher, &msg, NULL));

  // LED blinken als Heartbeat
  digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));

  rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
  delay(1000);
}
