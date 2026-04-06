#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <micro_ros_arduino.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/string.h>
#include <sensor_msgs/msg/magnetic_field.h>
#include <sensor_msgs/msg/range.h>
#include <geometry_msgs/msg/twist.h>
#include <nav_msgs/msg/odometry.h>
#include <rcl_interfaces/msg/log.h>

#include "config.h"
#include "oled_display.h"
#include "hmc5883l.h"
#include "srf02.h"
#include "md25.h"

// --- micro-ROS Objekte ---
rcl_node_t        node;

rcl_publisher_t   pub_status;
rcl_publisher_t   pub_compass;
rcl_publisher_t   pub_range;
rcl_publisher_t   pub_odom;

rcl_subscription_t sub_rosout;
rcl_subscription_t sub_cmd_vel;

std_msgs__msg__String            msg_status;
sensor_msgs__msg__MagneticField  msg_compass;
sensor_msgs__msg__Range          msg_range;
nav_msgs__msg__Odometry          msg_odom;
rcl_interfaces__msg__Log         msg_rosout;
geometry_msgs__msg__Twist        msg_cmd_vel;

// --- Odometrie-Zustand ---
static constexpr double METERS_PER_TICK = 0.3142 / 360.0;  // EMG30: 360 ticks, 100mm Rad
static constexpr double ODOM_WHEEL_BASE = 0.30;             // Spurbreite [m]
static int32_t odom_prev_enc1 = 0;
static int32_t odom_prev_enc2 = 0;
static double  odom_x     = 0.0;
static double  odom_y     = 0.0;
static double  odom_theta = 0.0;

rclc_executor_t  executor;
rclc_support_t   support;
rcl_allocator_t  allocator;

bool microros_initialized = false;

// --- cmd_vel Watchdog: Motoren stoppen wenn keine Message ---
static unsigned long last_cmd_vel_ms = 0;
static constexpr unsigned long CMD_VEL_TIMEOUT_MS = 500;

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

// --- /cmd_vel Subscriber-Callback ---
static void cmd_vel_cb(const void* msgin) {
    const geometry_msgs__msg__Twist* twist = (const geometry_msgs__msg__Twist*)msgin;
    md25_cmd_vel(twist->linear.x, twist->angular.z);
    last_cmd_vel_ms = millis();
}

// --- micro-ROS initialisieren (retry-fähig) ---
// Lokales Makro: zeigt Schritt auf OLED, gibt false zurück bei Fehler
#define RCCHECK_STEP(fn, step, name) { \
    oled_show_init_step(step, name); \
    if ((fn) != RCL_RET_OK) { \
        oled_show_init_step(-(step), name); \
        return false; \
    } \
}

bool microros_init() {
    allocator = rcl_get_default_allocator();

    RCCHECK_STEP(rclc_support_init(&support, 0, NULL, &allocator), 1, "support_init");
    RCCHECK_STEP(rclc_node_init_default(&node, NODE_NAME, NODE_NAMESPACE, &support), 2, "node_init");

    // Publisher
    RCCHECK_STEP(rclc_publisher_init_default(
        &pub_status, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
        TOPIC_STATUS), 3, "pub_status");

    RCCHECK_STEP(rclc_publisher_init_default(
        &pub_compass, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, MagneticField),
        TOPIC_COMPASS), 4, "pub_compass");

    RCCHECK_STEP(rclc_publisher_init_default(
        &pub_range, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, Range),
        TOPIC_STAIR), 5, "pub_range");

    RCCHECK_STEP(rclc_publisher_init_default(
        &pub_odom, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(nav_msgs, msg, Odometry),
        TOPIC_ODOM), 6, "pub_odom");

    // Subscriber
    RCCHECK_STEP(rclc_subscription_init_default(
        &sub_rosout, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(rcl_interfaces, msg, Log),
        "/rosout"), 7, "sub_rosout");

    RCCHECK_STEP(rclc_subscription_init_default(
        &sub_cmd_vel, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(geometry_msgs, msg, Twist),
        TOPIC_CMD_VEL), 8, "sub_cmd_vel");

    // Executor: 2 Subscriptions (rosout + cmd_vel) – Publisher brauchen keinen Handle
    RCCHECK_STEP(rclc_executor_init(&executor, &support.context, 2, &allocator), 9, "executor_init");
    RCCHECK_STEP(rclc_executor_add_subscription(
        &executor, &sub_rosout, &msg_rosout, &rosout_cb, ON_NEW_DATA), 10, "exec_add_rosout");
    RCCHECK_STEP(rclc_executor_add_subscription(
        &executor, &sub_cmd_vel, &msg_cmd_vel, &cmd_vel_cb, ON_NEW_DATA), 11, "exec_add_cmdvel");

    // --- Puffer allocieren (nur beim ersten Init) ---

    if (!msg_status.data.data) {
        msg_status.data.data     = (char*)malloc(64);
        msg_status.data.capacity = 64;
        msg_status.data.size     = 0;
    }

    if (!msg_rosout.msg.data) {
        msg_rosout.msg.data     = (char*)malloc(256);
        msg_rosout.msg.capacity = 256;
        msg_rosout.msg.size     = 0;
    }
    if (!msg_rosout.name.data) {
        msg_rosout.name.data     = (char*)malloc(64);
        msg_rosout.name.capacity = 64;
        msg_rosout.name.size     = 0;
    }

    // Odometry frame_ids (statisch, ändern sich nicht)
    static char frame_odom[]       = "odom";
    static char frame_base_link[]  = "base_link";
    msg_odom.header.frame_id.data        = frame_odom;
    msg_odom.header.frame_id.size        = strlen(frame_odom);
    msg_odom.header.frame_id.capacity    = sizeof(frame_odom);
    msg_odom.child_frame_id.data         = frame_base_link;
    msg_odom.child_frame_id.size         = strlen(frame_base_link);
    msg_odom.child_frame_id.capacity     = sizeof(frame_base_link);
    // Kovarianzen auf 0 (unbekannt)
    memset(msg_odom.pose.covariance,  0, sizeof(msg_odom.pose.covariance));
    memset(msg_odom.twist.covariance, 0, sizeof(msg_odom.twist.covariance));

    // Compass frame_id (statisch, ändert sich nicht)
    msg_compass.header.frame_id.data     = frame_base_link;
    msg_compass.header.frame_id.size     = strlen(frame_base_link);
    msg_compass.header.frame_id.capacity = sizeof(frame_base_link);

    // Range: Konstante Felder einmalig setzen
    static char frame_range[] = "stair_sensor";
    msg_range.header.frame_id.data     = frame_range;
    msg_range.header.frame_id.size     = strlen(frame_range);
    msg_range.header.frame_id.capacity = sizeof(frame_range);
    msg_range.radiation_type = sensor_msgs__msg__Range__ULTRASOUND;
    msg_range.field_of_view  = 0.524f;   // ~30° in rad (SRF02 Kegelwinkel)
    msg_range.min_range      = 0.16f;    // 16 cm Mindestabstand SRF02
    msg_range.max_range      = 6.00f;    // 600 cm Maximalabstand SRF02
    msg_range.variance       = 0.0f;

    return true;
}

// --- micro-ROS aufräumen vor Retry ---
void microros_cleanup() {
    rcl_subscription_fini(&sub_cmd_vel, &node);
    rcl_subscription_fini(&sub_rosout, &node);
    rcl_publisher_fini(&pub_odom, &node);
    rcl_publisher_fini(&pub_range, &node);
    rcl_publisher_fini(&pub_compass, &node);
    rcl_publisher_fini(&pub_status, &node);
    rcl_node_fini(&node);
    rclc_support_fini(&support);
    md25_stop();
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);

    Serial.println(F("[R2D2] Booting..."));

    Wire.begin(I2C0_SDA_PIN, I2C0_SCL_PIN);

    if (!hmc5883l_init()) {
        Serial.println(F("[R2D2] WARN: HMC5883L init fehlgeschlagen"));
    }

    md25_init();
    md25_stop();
    uint8_t md25_ver = md25_get_version();
    if (md25_ver) {
        Serial.printf("[R2D2] MD25 gefunden, SW-Version: %u\n", md25_ver);
    } else {
        Serial.println(F("[R2D2] WARN: MD25 nicht erreichbar (Timeout)"));
    }

    oled_init();
    set_microros_transports();

    Serial.println(F("[R2D2] Setup abgeschlossen, warte auf micro-ROS Agent..."));
}

void loop() {
    unsigned long now    = millis();
    unsigned long uptime = now / 1000;

    // --- Reconnect-Loop: versucht Agent zu erreichen bis es klappt ---
    if (!microros_initialized) {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
        delay(500);

        oled_update(false, uptime);
        Serial.println(F("[R2D2] Warte auf micro-ROS Agent..."));

        if (microros_init()) {
            microros_initialized = true;
            last_cmd_vel_ms = now;
            digitalWrite(LED_BUILTIN, HIGH);
            Serial.println(F("[R2D2] micro-ROS verbunden!"));
            Serial.printf("  Node:    %s\n", NODE_NAME);
            Serial.printf("  Compass: %s\n", TOPIC_COMPASS);
            Serial.printf("  Range:   %s\n", TOPIC_STAIR);
            Serial.printf("  CmdVel:  %s\n", TOPIC_CMD_VEL);
            oled_update(true, uptime);
        }
        return;
    }

    // --- cmd_vel Watchdog: Motoren stoppen bei Ausbleiben ---
    if (now - last_cmd_vel_ms >= CMD_VEL_TIMEOUT_MS) {
        md25_stop();
    }

    // --- Status Heartbeat @ 1 Hz ---
    static unsigned long last_status = 0;
    if (now - last_status >= HEARTBEAT_MS) {
        last_status = now;

        snprintf(msg_status.data.data, msg_status.data.capacity,
                 "R2D2 Chassis Online | uptime: %lus", uptime);
        msg_status.data.size = strlen(msg_status.data.data);

        if (rcl_publish(&pub_status, &msg_status, NULL) != RCL_RET_OK) {
            Serial.println(F("[R2D2] Verbindung verloren, reconnect..."));
            microros_cleanup();
            microros_initialized = false;
            oled_update(false, uptime);
            return;
        }
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }

    // --- Compass @ 10 Hz ---
    static unsigned long last_compass = 0;
    if (now - last_compass >= 100) {
        last_compass = now;

        float x_T, y_T, z_T;
        if (hmc5883l_read(&x_T, &y_T, &z_T)) {
            msg_compass.magnetic_field.x = x_T;
            msg_compass.magnetic_field.y = y_T;
            msg_compass.magnetic_field.z = z_T;
            RCSOFTCHECK(rcl_publish(&pub_compass, &msg_compass, NULL));
        }
    }

    // --- SRF02 @ 5 Hz, non-blocking (trigger → 70ms → read) ---
    static unsigned long srf02_trigger_at = 0;
    static bool          srf02_pending    = false;

    if (!srf02_pending && now - srf02_trigger_at >= 200) {
        srf02_trigger();
        srf02_trigger_at = now;
        srf02_pending    = true;
    }
    if (srf02_pending && now - srf02_trigger_at >= 70) {
        uint16_t dist_cm;
        if (srf02_read_cm(&dist_cm)) {
            msg_range.range = dist_cm / 100.0f;   // cm → m
            RCSOFTCHECK(rcl_publish(&pub_range, &msg_range, NULL));
        }
        srf02_pending = false;
    }

    // --- Odometrie @ 10 Hz ---
    static unsigned long last_odom = 0;
    if (now - last_odom >= 100) {
        unsigned long dt_ms = now - last_odom;
        last_odom = now;

        int32_t enc1, enc2;
        if (md25_get_encoders(&enc1, &enc2)) {
            double delta_left  = (enc1 - odom_prev_enc1) * METERS_PER_TICK;
            double delta_right = (enc2 - odom_prev_enc2) * METERS_PER_TICK;
            odom_prev_enc1 = enc1;
            odom_prev_enc2 = enc2;

            double delta_dist  = (delta_left + delta_right) / 2.0;
            double delta_theta = (delta_right - delta_left) / ODOM_WHEEL_BASE;

            odom_x     += delta_dist * cos(odom_theta + delta_theta / 2.0);
            odom_y     += delta_dist * sin(odom_theta + delta_theta / 2.0);
            odom_theta += delta_theta;

            double dt_s = dt_ms / 1000.0;

            // Pose
            msg_odom.pose.pose.position.x = odom_x;
            msg_odom.pose.pose.position.y = odom_y;
            msg_odom.pose.pose.position.z = 0.0;
            // Quaternion aus theta (Rotation um Z)
            msg_odom.pose.pose.orientation.x = 0.0;
            msg_odom.pose.pose.orientation.y = 0.0;
            msg_odom.pose.pose.orientation.z = sin(odom_theta / 2.0);
            msg_odom.pose.pose.orientation.w = cos(odom_theta / 2.0);

            // Twist (Geschwindigkeit im base_link Frame)
            msg_odom.twist.twist.linear.x  = delta_dist  / dt_s;
            msg_odom.twist.twist.angular.z = delta_theta / dt_s;

            RCSOFTCHECK(rcl_publish(&pub_odom, &msg_odom, NULL));
        }
    }

    // --- Executor: Subscriptions abarbeiten ---
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(SPIN_TIMEOUT_MS));

    oled_update(true, uptime);
}
