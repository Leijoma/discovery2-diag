// kline_node.ino — ESP32 K-line node: WiFi + OTA + web + K-line test.
//
// Foundation for the node/standalone firmware. Built on the ESP32 Arduino core ONLY.
//   - WiFi: multi-network with PRIORITY — WIFI_SSID_1 (SurfsUp) first, then
//     WIFI_SSID_2 (Surfs, phone hotspot). Mirrors the Pi's wlan1 fallback chain.
//   - OTA: after the first USB flash, later flashes go over WiFi (password-gated).
//   - Web: status page + /status JSON + /scan (fast init + StartCommunication to
//     TD5 0x13 and SLABS 0x29, shows the ECU response — test the car from a browser).
//
// K-line runs on the Arduino loop (core 1 by default); the WiFi stack runs on core 0,
// so the fast-init timing is already isolated from WiFi. Wiring is the proven L9637D
// setup (see hardware/README.md): RX pin1→GPIO16, TX pin4→GPIO17, VS→12V, K→OBD7 +
// 1 kΩ pull-up to 12 V, common ground. KLINE_INVERT=false (L9637D is non-inverting).
//
// Credentials in secrets.h (gitignored — copy secrets.example.h). Repo is public.

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include "secrets.h"

static WebServer server(80);
static uint32_t bootMs = 0;

// ---------------- K-line ----------------
static const int      PIN_KRX      = 16;      // L9637D pin 1 (RX) -> GPIO16
static const int      PIN_KTX      = 17;      // GPIO17 -> L9637D pin 4 (TX)
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = false;   // L9637D is non-inverting
static const uint8_t  TESTER_ADDR  = 0xF7;

static uint8_t checksum(const uint8_t *d, size_t n) {
  uint16_t s = 0; for (size_t i = 0; i < n; i++) s += d[i]; return (uint8_t)(s & 0xFF);
}
static String toHex(const uint8_t *d, size_t n) {
  String s; char b[4];
  for (size_t i = 0; i < n; i++) { snprintf(b, sizeof b, "%02X ", d[i]); s += b; }
  s.trim(); return s;
}
static size_t readBytes(uint8_t *buf, size_t n, uint32_t timeout_ms) {
  size_t got = 0; uint32_t t0 = millis();
  while (got < n && millis() - t0 < timeout_ms)
    while (Serial2.available() && got < n) buf[got++] = (uint8_t)Serial2.read();
  return got;
}
static void stopComm() {                       // best-effort clear of any open link
  uint8_t s[3] = { 0x01, 0x82, 0x83 };
  Serial2.write(s, 3); Serial2.flush(); delay(30);
  while (Serial2.available()) Serial2.read();
}
static void klineFastInit() {                  // ISO 14230-2 fast init
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(300);   // W5 idle
  digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW); delay(25);    // 25 ms low
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(25);    // 25 ms high
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
}
// One module: fast init + StartCommunication; returns a human-readable result line.
static String kwpStartComm(uint8_t addr, const char *name) {
  stopComm();
  klineFastInit();
  uint8_t req[5] = { 0x81, addr, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);
  while (Serial2.available()) Serial2.read();
  Serial2.write(req, 5); Serial2.flush();
  uint8_t echo[5]; size_t e = readBytes(echo, 5, 300);
  uint8_t resp[16]; size_t r = readBytes(resp, sizeof resp, 500);
  bool ok = false; for (size_t i = 0; i < r; i++) if (resp[i] == 0xC1) { ok = true; break; }
  char hdr[24]; snprintf(hdr, sizeof hdr, "%s (0x%02X)", name, addr);
  return String(hdr) + ": TX " + toHex(req, 5) +
         " | ECHO " + (e ? toHex(echo, e) : String("-")) +
         " | RX " + (r ? toHex(resp, r) : String("(no response)")) +
         (ok ? "   OK C1" : "");
}

// ---------------- WiFi ----------------
struct WifiNet { const char *ssid; const char *pw; };
static const WifiNet NETS[] = { {WIFI_SSID_1, WIFI_PW_1}, {WIFI_SSID_2, WIFI_PW_2} };

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
    WiFi.disconnect(true); delay(200);
  }
  Serial.println("WiFi: no known network in range");
  return false;
}

// ---------------- Web ----------------
static String uptimeStr() {
  uint32_t s = (millis() - bootMs) / 1000; char b[32];
  snprintf(b, sizeof b, "%lud %02lu:%02lu:%02lu", s/86400, (s/3600)%24, (s/60)%60, s%60);
  return String(b);
}
static void handleRoot() {
  String ssid = WiFi.SSID();
  String html =
    "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
    "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#0b0b0c;color:#eee}"
    "h1{font-size:20px}li{margin:4px 0}code{color:#7fd4ff}"
    "a.btn{display:inline-block;margin-top:14px;padding:12px 18px;background:#1e6feb;color:#fff;"
    "border-radius:10px;text-decoration:none;font-weight:600}</style>"
    "<h1>K-line node</h1><ul>"
    "<li>WiFi: <code>" + (ssid.length()?ssid:String("(disconnected)")) + "</code></li>"
    "<li>IP: <code>" + WiFi.localIP().toString() + "</code></li>"
    "<li>RSSI: <code>" + String(WiFi.RSSI()) + " dBm</code></li>"
    "<li>Uptime: <code>" + uptimeStr() + "</code></li></ul>"
    "<a class=btn href='/scan'>Test car (TD5 + SLABS)</a>"
    "<p style='color:#888;font-size:13px'>Ignition on, node wired to OBD (K/12V/GND + 1k pull-up).</p>";
  server.send(200, "text/html", html);
}
static void handleStatus() {
  server.send(200, "application/json",
    "{\"ssid\":\"" + WiFi.SSID() + "\",\"ip\":\"" + WiFi.localIP().toString() +
    "\",\"rssi\":" + String(WiFi.RSSI()) + ",\"uptime_s\":" + String((millis()-bootMs)/1000) + "}");
}
static void handleScan() {
  String out = kwpStartComm(0x13, "TD5") + "\n" + kwpStartComm(0x29, "SLABS") + "\n";
  server.send(200, "text/plain", out);
}

void setup() {
  Serial.begin(115200); delay(300); bootMs = millis();
  Serial.println("\n== K-line node: WiFi + OTA + web + K-line ==");
  WiFi.mode(WIFI_STA); WiFi.setHostname(OTA_HOSTNAME); WiFi.setAutoReconnect(true);
  wifiConnect();

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.begin();

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.on("/scan", handleScan);
  server.begin();
  Serial.printf("Web http://%s/  · /scan tests the car · OTA '%s'.\n",
                WiFi.localIP().toString().c_str(), OTA_HOSTNAME);
}

static uint32_t lastWifiCheck = 0;
void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiCheck > 10000) {
    lastWifiCheck = millis();
    Serial.println("WiFi: link down, reconnecting ...");
    wifiConnect();
  }
}
