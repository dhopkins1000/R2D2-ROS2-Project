#include <Arduino.h>
#include <Wire.h>
#include <micro_ros_arduino.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/string.h>
#include <rcl_interfaces/msg/log.h>

#include "config.h"
#include "oled_display.h"

// --- micro-ROS Objekte ---
rcl_node_t        node;
rcl_publisher_t   pub_status;
rcl_subscription_t sub_rosout;

std_msgs__msg__String      msg_status;
rcl_interfaces__msg__Log   msg_rosout;

rclc_executor_t  executor;
rclc_support_t   support;
rcl_allocator_t  allocator;

bool microros_initialized = false;

// --- Fehlerbehandlung ---
#define RCCHECK(fn)     { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) return false; }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

// --- /rosout Subscriber-Callback ---
static void rosout_cb(const void* msgin) {
    const rcl_interfaces__msg__Log* log = (const rcl_interfaces__msg__Log*)msgin;
    if (log->msg.data && log->msg.size > 0) {
        oled_push_log(log->msg.data);
    }
}

// --- micro-ROS initialisieren (retry-fähig) ---
bool microros_init() {
    allocator = rcl_get_default_allocator();

    if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
    if (rclc_node_init_default(&node, NODE_NAME, NODE_NAMESPACE, &support) != RCL_RET_OK) return false;

    // Status-Publisher
    RCCHECK(rclc_publisher_init_default(
        &pub_status,
        &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
        TOPIC_STATUS
    ));

    // /rosout Subscriber
    RCCHECK(rclc_subscription_init_default(
        &sub_rosout,
        &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(rcl_interfaces, msg, Log),
        "/rosout"
    ));

    // Executor: 1 Handle für den /rosout Subscriber
    RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
    RCCHECK(rclc_executor_add_subscription(
        &executor, &sub_rosout, &msg_rosout, &rosout_cb, ON_NEW_DATA
    ));

    // Status-Message Puffer
    if (!msg_status.data.data) {
        msg_status.data.data     = (char*)malloc(64 * sizeof(char));
        msg_status.data.capacity = 64;
        msg_status.data.size     = 0;
    }

    // /rosout Message Puffer – nur msg und name Felder benötigt
    if (!msg_rosout.msg.data) {
        msg_rosout.msg.data     = (char*)malloc(256 * sizeof(char));
        msg_rosout.msg.capacity = 256;
        msg_rosout.msg.size     = 0;
    }
    if (!msg_rosout.name.data) {
        msg_rosout.name.data     = (char*)malloc(64 * sizeof(char));
        msg_rosout.name.capacity = 64;
        msg_rosout.name.size     = 0;
    }

    return true;
}

// --- micro-ROS aufräumen vor Retry ---
void microros_cleanup() {
    rcl_subscription_fini(&sub_rosout, &node);
    rcl_publisher_fini(&pub_status, &node);
    rcl_node_fini(&node);
    rclc_support_fini(&support);
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);

    Serial.println(F("[R2D2 Chassis] Booting..."));

    oled_init();

    set_microros_transports();

    // TODO: MD25 UART init

    // I2C Bus 0 (SDA=21, SCL=22) – HMC5883L auf 0x1E verifiziert
    Wire.begin(21, 22);
}

void loop() {
    unsigned long now     = millis();
    unsigned long uptime  = now / 1000;

    // --- Reconnect-Loop: versucht Agent zu erreichen bis es klappt ---
    if (!microros_initialized) {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));  // Langsames Blinken = warte auf Agent
        delay(500);

        oled_update(false, uptime);
        Serial.println(F("[R2D2 Chassis] Warte auf micro-ROS Agent..."));

        if (microros_init()) {
            microros_initialized = true;
            digitalWrite(LED_BUILTIN, HIGH);
            Serial.println(F("[R2D2 Chassis] micro-ROS verbunden!"));
            Serial.printf("  Node:  %s\n", NODE_NAME);
            Serial.printf("  Topic: %s\n", TOPIC_STATUS);
            oled_update(true, uptime);
        }
        return;
    }

    // --- Normaler Betrieb ---
    static unsigned long last_publish = 0;

    if (now - last_publish >= HEARTBEAT_MS) {
        last_publish = now;

        snprintf(msg_status.data.data, msg_status.data.capacity,
                 "R2D2 Chassis Online | uptime: %lus", uptime);
        msg_status.data.size = strlen(msg_status.data.data);

        if (rcl_publish(&pub_status, &msg_status, NULL) != RCL_RET_OK) {
            // Verbindung verloren – neu verbinden
            Serial.println(F("[R2D2 Chassis] Verbindung verloren, reconnect..."));
            microros_cleanup();
            microros_initialized = false;
            oled_update(false, uptime);
            return;
        }

        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));  // Heartbeat LED
    }

    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(SPIN_TIMEOUT_MS));

    oled_update(true, uptime);
}
