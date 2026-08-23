// kline_node.ino — ESP32 K-line node: WiFi + OTA + a small web server.
//
// Foundation for the node/standalone firmware. The proven K-line bring-up lives in
// esp32/kline_test — the K-line engine (init · send-frame→response · keepalive) gets
// folded in here later, pinned to core 1 while WiFi/web run on core 0.
//
// Built on the ESP32 Arduino core ONLY — no external libraries.
//   - WiFi: multi-network with PRIORITY — WIFI_SSID_1 (SurfsUp) first, then
//     WIFI_SSID_2 (Surfs, phone hotspot). Mirrors the Pi's wlan1 fallback chain.
//   - OTA: after the first USB flash, later flashes can go over WiFi
//     (arduino-cli upload -p <ip> …, or the Arduino IDE network port). Password-gated.
//   - Web: a status page on port 80 + /status JSON.
//
// Credentials are in secrets.h (gitignored — copy secrets.example.h). The repo is
// public, so real SSIDs/passwords must never be committed.

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include "secrets.h"

static WebServer server(80);
static uint32_t bootMs = 0;

struct WifiNet { const char *ssid; const char *pw; };
static const WifiNet NETS[] = { {WIFI_SSID_1, WIFI_PW_1}, {WIFI_SSID_2, WIFI_PW_2} };

// Try each configured network in priority order; connect to the first that answers.
static bool wifiConnect() {
  for (auto &n : NETS) {
    if (!n.ssid || !*n.ssid) continue;
    Serial.printf("WiFi: trying %s ...\n", n.ssid);
    WiFi.begin(n.ssid, n.pw);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) delay(200);
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("WiFi: connected to %s  IP %s  RSSI %d dBm\n",
                    n.ssid, WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
    }
    WiFi.disconnect(true);
    delay(200);
  }
  Serial.println("WiFi: no known network in range");
  return false;
}

static String uptimeStr() {
  uint32_t s = (millis() - bootMs) / 1000;
  char b[32];
  snprintf(b, sizeof b, "%lud %02lu:%02lu:%02lu", s / 86400, (s / 3600) % 24, (s / 60) % 60, s % 60);
  return String(b);
}

static void handleRoot() {
  String ssid = WiFi.SSID();
  String html =
    "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
    "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#0b0b0c;color:#eee}"
    "h1{font-size:20px}li{margin:4px 0}code{color:#7fd4ff}</style>"
    "<h1>K-line node</h1><ul>"
    "<li>WiFi: <code>" + (ssid.length() ? ssid : String("(disconnected)")) + "</code></li>"
    "<li>IP: <code>" + WiFi.localIP().toString() + "</code></li>"
    "<li>RSSI: <code>" + String(WiFi.RSSI()) + " dBm</code></li>"
    "<li>Uptime: <code>" + uptimeStr() + "</code></li>"
    "<li>K-line: <code>not wired in yet</code></li>"
    "</ul><p>OTA enabled. JSON: <a href='/status' style='color:#7fd4ff'>/status</a></p>";
  server.send(200, "text/html", html);
}

static void handleStatus() {
  String j = "{\"ssid\":\"" + WiFi.SSID() + "\",\"ip\":\"" + WiFi.localIP().toString() +
             "\",\"rssi\":" + String(WiFi.RSSI()) +
             ",\"uptime_s\":" + String((millis() - bootMs) / 1000) + "}";
  server.send(200, "application/json", j);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  bootMs = millis();
  Serial.println("\n== K-line node: WiFi + OTA + web ==");

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(OTA_HOSTNAME);
  WiFi.setAutoReconnect(true);
  wifiConnect();

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([] { Serial.println("OTA: start"); });
  ArduinoOTA.onEnd([]   { Serial.println("OTA: done"); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA: error %u\n", e); });
  ArduinoOTA.begin();

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.begin();
  Serial.printf("Web server on http://%s/ ; OTA ready as '%s'.\n",
                WiFi.localIP().toString().c_str(), OTA_HOSTNAME);
}

static uint32_t lastWifiCheck = 0;
void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  // Re-try the priority chain if the link drops (every 10 s).
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiCheck > 10000) {
    lastWifiCheck = millis();
    Serial.println("WiFi: link down, reconnecting ...");
    wifiConnect();
  }
}
