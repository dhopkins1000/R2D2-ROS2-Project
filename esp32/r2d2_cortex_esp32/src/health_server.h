#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "config.h"
#include "battery.h"
#include "power.h"

class HealthServer {
public:
    void begin(BatteryMonitor* battery, PowerManager* power);
    void update();               // call every loop()
    void enableAP();             // switch to AP mode
    void disableAP();            // back to STA mode
    bool isAPActive() const { return _apActive; }
    bool wakeRequested();        // returns true once if wake requested via web
    bool sleepRequested();       // returns true once if sleep requested via web
    void clearWakeRequest() { _wakeRequested = false; }
    void clearSleepRequest() { _sleepRequested = false; }
    String getIP() const;

private:
    BatteryMonitor* _battery = nullptr;
    PowerManager* _power = nullptr;
    WebServer _server{HTTP_PORT};
    bool _apActive = false;
    bool _wifiConnected = false;
    bool _serverStarted = false;
    volatile bool _wakeRequested = false;
    volatile bool _sleepRequested = false;

    void startServer();
    void handleRoot();
    void handleStatus();
    void handleWake();
    void handleSleep();
    String buildHealthPage();
    String buildStatusJson();
};
