#include "health_server.h"

void HealthServer::begin(BatteryMonitor* battery, PowerManager* power) {
    _battery = battery;
    _power = power;

    // Try STA connection
    Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        _wifiConnected = true;
        Serial.printf("[WIFI] Connected. IP=%s\n", WiFi.localIP().toString().c_str());
        startServer();
    } else {
        Serial.println("[WIFI] Connection failed. Continuing offline.");
    }
}

void HealthServer::enableAP() {
    WiFi.disconnect(true);
    delay(100);
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(AP_IP, AP_IP, IPAddress(255, 255, 255, 0));
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    _apActive = true;
    _wifiConnected = false;
    Serial.printf("[WIFI] AP mode: SSID=%s IP=%s\n", AP_SSID, WiFi.softAPIP().toString().c_str());

    if (!_serverStarted) {
        startServer();
    }
}

void HealthServer::disableAP() {
    WiFi.softAPdisconnect(true);
    _apActive = false;
    Serial.println("[WIFI] AP disabled. Reconnecting STA...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(500);
    }
    if (WiFi.status() == WL_CONNECTED) {
        _wifiConnected = true;
        Serial.printf("[WIFI] Reconnected. IP=%s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("[WIFI] Reconnection failed.");
    }
}

String HealthServer::getIP() const {
    if (_apActive) return WiFi.softAPIP().toString();
    if (_wifiConnected) return WiFi.localIP().toString();
    return "N/A";
}

void HealthServer::startServer() {
    _server.on("/", HTTP_GET, [this]() { handleRoot(); });
    _server.on("/status", HTTP_GET, [this]() { handleStatus(); });
    _server.on("/wake", HTTP_POST, [this]() { handleWake(); });
    _server.on("/sleep", HTTP_POST, [this]() { handleSleep(); });
    _server.begin();
    _serverStarted = true;
    Serial.printf("[HTTP] Health server running at http://%s\n", getIP().c_str());
}

void HealthServer::update() {
    if (_serverStarted) {
        _server.handleClient();
    }
}

bool HealthServer::wakeRequested() {
    if (_wakeRequested) {
        _wakeRequested = false;
        return true;
    }
    return false;
}

bool HealthServer::sleepRequested() {
    if (_sleepRequested) {
        _sleepRequested = false;
        return true;
    }
    return false;
}

void HealthServer::handleRoot() {
    _server.send(200, "text/html", buildHealthPage());
}

void HealthServer::handleStatus() {
    _server.send(200, "application/json", buildStatusJson());
}

void HealthServer::handleWake() {
    _wakeRequested = true;
    _server.send(200, "text/plain", "Wake command received.");
}

void HealthServer::handleSleep() {
    _sleepRequested = true;
    _server.send(200, "text/plain", "Sleep command received.");
}

String HealthServer::buildStatusJson() {
    const BatteryData& b = _battery->getData();

    String json = "{";
    json += "\"vbat\":" + String(b.vbat, 2);
    json += ",\"soc\":" + String(b.soc, 1);
    json += ",\"ibat\":" + String(b.ibat, 2);
    json += ",\"temp\":" + String(b.temp, 1);
    json += ",\"mode\":\"" + String(BatteryMonitor::modeName(b.mode)) + "\"";
    json += ",\"alarm\":" + String(b.alarm);
    json += ",\"alarm_name\":\"" + String(BatteryMonitor::alarmName(b.alarm)) + "\"";
    json += ",\"charger\":" + String(b.charger_connected ? "true" : "false");
    json += ",\"pi_on\":" + String(_power->getPiPower() ? "true" : "false");
    json += ",\"motors_on\":" + String(_power->getMD25Power() ? "true" : "false");
    json += ",\"uptime_s\":" + String(millis() / 1000);
    json += ",\"wifi_mode\":\"" + String(_apActive ? "AP" : "STA") + "\"";
    json += ",\"ip\":\"" + getIP() + "\"";
    json += "}";
    return json;
}

String HealthServer::buildHealthPage() {
    const BatteryData& b = _battery->getData();

    String html = R"rawhtml(<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>R2D2 Status</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a2e;color:#e0e0e0;font-family:monospace;padding:16px;max-width:480px;margin:0 auto}
h1{color:#0ff;font-size:1.4em;margin-bottom:12px;text-align:center}
.card{background:#16213e;border-radius:8px;padding:12px;margin-bottom:10px}
.card h2{color:#0af;font-size:1em;margin-bottom:8px}
.row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1a1a3e}
.row:last-child{border:none}
.label{color:#888}.val{color:#0f0;font-weight:bold}
.warn{color:#ff0}.crit{color:#f00}
.btn{display:block;width:100%;padding:12px;margin:6px 0;border:none;border-radius:6px;
font-size:1em;font-family:monospace;cursor:pointer}
.btn-wake{background:#0a5;color:#fff}
.btn-sleep{background:#a00;color:#fff}
.btn:active{opacity:0.7}
.footer{text-align:center;color:#555;font-size:0.8em;margin-top:12px}
</style></head><body>
<h1>R2D2 Cortex Status</h1>
)rawhtml";

    // Battery card
    html += "<div class='card'><h2>Battery</h2>";
    html += "<div class='row'><span class='label'>Voltage</span><span class='val'>" + String(b.vbat, 2) + " V</span></div>";

    String socClass = "val";
    if (b.soc < 20.0f) socClass = "crit";
    else if (b.soc < 50.0f) socClass = "warn";
    html += "<div class='row'><span class='label'>SOC</span><span class='" + socClass + "'>" + String(b.soc, 1) + " %</span></div>";

    html += "<div class='row'><span class='label'>Current</span><span class='val'>" + String(b.ibat, 2) + " A</span></div>";
    html += "<div class='row'><span class='label'>Temperature</span><span class='val'>" + String(b.temp, 1) + " &deg;C</span></div>";
    html += "<div class='row'><span class='label'>Charger</span><span class='val'>" + String(b.charger_connected ? "Connected" : "None") + "</span></div>";
    html += "<div class='row'><span class='label'>Mode</span><span class='val'>" + String(BatteryMonitor::modeName(b.mode)) + "</span></div>";
    html += "<div class='row'><span class='label'>Alarm</span><span class='val'>" + String(BatteryMonitor::alarmName(b.alarm)) + "</span></div>";
    html += "</div>";

    // Power card
    html += "<div class='card'><h2>Power</h2>";
    html += "<div class='row'><span class='label'>Pi</span><span class='val'>" + String(_power->getPiPower() ? "ON" : "OFF") + "</span></div>";
    html += "<div class='row'><span class='label'>Motors</span><span class='val'>" + String(_power->getMD25Power() ? "ON" : "OFF") + "</span></div>";
    html += "</div>";

    // Network card
    html += "<div class='card'><h2>Network</h2>";
    html += "<div class='row'><span class='label'>WiFi Mode</span><span class='val'>" + String(_apActive ? "AP" : "STA") + "</span></div>";
    html += "<div class='row'><span class='label'>IP</span><span class='val'>" + getIP() + "</span></div>";
    html += "<div class='row'><span class='label'>Uptime</span><span class='val'>" + String(millis() / 1000) + " s</span></div>";
    html += "</div>";

    // Control buttons with JS confirm dialogs
    html += R"rawhtml(
<form method="POST" action="/wake" onsubmit="return confirm('Wake R2D2?')">
<button class="btn btn-wake" type="submit">Wake R2D2</button></form>
<form method="POST" action="/sleep" onsubmit="return confirm('Put R2D2 to sleep?')">
<button class="btn btn-sleep" type="submit">Sleep R2D2</button></form>
<div class="footer">R2D2 Cortex ESP32 &bull; Auto-refresh 5s</div>
</body></html>)rawhtml";

    return html;
}
