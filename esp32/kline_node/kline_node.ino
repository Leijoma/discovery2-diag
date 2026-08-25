// kline_node.ino — ESP32 K-line node: WiFi + OTA + web + K-line + InfluxDB logging.
//
// Standalone node firmware. ESP32 Arduino core only.
//   - WiFi: multi-network with PRIORITY — WIFI_SSID_1 (SurfsUp) first, then
//     WIFI_SSID_2 (Surfs, phone hotspot). Mirrors the Pi's wlan1 fallback chain.
//   - OTA: after the first USB flash, later flashes go over WiFi (password-gated).
//   - WireGuard: fixed tunnel IP so the node is reachable from the phone regardless
//     of the hotspot DHCP address (see hardware/README.md).
//   - Web: status page + /status JSON + /scan (fast init + StartCommunication) + /log.
//   - LOGGING: establishes a full Td5 session (fast init → StartCommunication →
//     StartDiagnosticSession 0xA0 → SecurityAccess seed→key) and reads a curated set
//     of LIDs ~1 Hz, decodes them to physical units, and POSTs Influx line protocol to
//     the home server. The WG server IS the Influx box (10.9.0.1), so the same address
//     works on home WiFi and over WG in the car. Data lands in the `disco` bucket while
//     the node has any uplink — no SD, no Pi-in-car needed.
//
// K-line runs on the Arduino loop (core 1 by default); the WiFi stack runs on core 0,
// so fast-init timing is isolated from WiFi. Wiring is the proven L9637D setup
// (hardware/README.md): RX pin1→GPIO16, TX pin4→GPIO17, VS→12V, K→OBD7 + 1 kΩ pull-up
// to 12 V, common ground. KLINE_INVERT=false (L9637D is non-inverting).
//
// Credentials in secrets.h (gitignored — copy secrets.example.h). Repo is public.

#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include <ESPmDNS.h>
#include <WireGuard-ESP32.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <time.h>
#include "secrets.h"
#include "kline_core.h"          // K-line/KWP2000/Td5 comms core (no WiFi/Influx/web)

static WebServer server(80);
static WireGuard wg;
static bool wgUp = false;
static WiFiUDP kaUdp;
static uint32_t bootMs = 0;

// Logging + raw-capture state (declared early so the K-line layer can append raw frames).
static bool     logEnabled = false;    // decoded logging (Influx) + raw capture master switch
static bool     rawOn      = false;    // raw TX/RX streaming configured/enabled
static String   rawBuf;                // pending raw lines, flushed to the collector
static uint32_t lastRawFlush = 0;
static int      lastRawCode = 0;       // last raw POST HTTP code

// Coverage sweep: unmapped LIDs the reference tool polls (fuelling/switch blocks). Read
// ONE per cycle, round-robin — raw-captured for RE, not decoded. Mirrors _TD5_COVERAGE_EXTRA.
static const uint8_t SWEEP[] = { 0x1E, 0x1F, 0x20, 0x36 };
static const size_t  NSWEEP  = sizeof SWEEP / sizeof SWEEP[0];

// --- raw TX/RX capture: append one line in the `--raw-log` format so the server's
//     tools/raw_analyze.py reads it unchanged (`<ISO8601-UTC> TX|RX <hex>`). ---
static String rawTs() {
  time_t t = time(nullptr);
  if (t < 1700000000) return String("1970-01-01T00:00:00.000Z");   // pre-NTP fallback
  struct tm g; gmtime_r(&t, &g);
  char b[40];
  snprintf(b, sizeof b, "%04d-%02d-%02dT%02d:%02d:%02d.%03luZ",
           g.tm_year + 1900, g.tm_mon + 1, g.tm_mday, g.tm_hour, g.tm_min, g.tm_sec,
           (unsigned long)(millis() % 1000));
  return String(b);
}
static void rawCapture(const char *dir, const uint8_t *d, size_t n) {
  if (!(logEnabled && rawOn) || n == 0) return;
  if (rawBuf.length() > 28000) return;             // safety cap until the next flush
  rawBuf += rawTs(); rawBuf += ' '; rawBuf += dir; rawBuf += ' ';
  rawBuf += toHex(d, n); rawBuf += '\n';
}

// ---------------- InfluxDB logging ----------------
static bool     sessionUp    = false;
static uint32_t lastCycle    = 0;
static uint32_t lastBeat     = 0;
static int      lastPost     = 0;      // last engine POST HTTP code (0 = none yet)
static uint32_t pointsSent   = 0;
static uint32_t estabFails   = 0;
// On-node fuel computer (derive at the source). Trip = since boot (= since the car/node
// powered on for this drive). Same math + constants as Python _FuelComputer.
static double   tripFuel     = 0.0;    // litres, this trip
static double   tripDist     = 0.0;    // km, this trip
static uint32_t lastFuelMs   = 0;      // last integration tick (0 = not started)
// Stale-link recovery: a link left open (e.g. a reflash mid-session) makes the module
// answer 7F 81 10 to every StartCommunication until it times out. The ONLY thing that
// clears it is bus SILENCE — sending 82/init during the wait resets the module's timer
// (proven on the KKL stack). So: send 82 ONCE (linkMaybeOpen), then stay off the bus
// until quietUntil, then init clean.
static bool     linkMaybeOpen = true;  // assume a leftover link at boot
static uint32_t quietUntil    = 0;     // don't touch K-line before this (ms)
static const uint32_t LOG_INTERVAL_MS   = 1000;
static const uint32_t ESTAB_QUIET_MS    = 6000;   // bus-silent window that lets a stale link die
static const uint32_t BEAT_INTERVAL_MS  = 15000;  // node heartbeat cadence

static bool influxConfigured() {
  return strlen(INFLUX_TOKEN) > 20 && strncmp(INFLUX_TOKEN, "influx-write", 12) != 0;
}
static int influxPost(const String &body) {
  if (!wgUp) return -3;                        // no route to 10.9.0.1 without the tunnel
  if (WiFi.status() != WL_CONNECTED) return -1;
  HTTPClient http;
  String url = String(INFLUX_URL) + "/api/v2/write?org=" + INFLUX_ORG +
               "&bucket=" + INFLUX_BUCKET + "&precision=s";
  http.setConnectTimeout(2000);
  http.setTimeout(3000);
  if (!http.begin(url)) return -2;
  http.addHeader("Authorization", String("Token ") + INFLUX_TOKEN);
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  int code = http.POST((uint8_t *)body.c_str(), body.length());
  http.end();
  return code;
}
static long epochNow() {
  time_t t = time(nullptr);
  return (t > 1700000000) ? (long)t : 0;      // 0 → let Influx stamp server time
}
static bool rawConfigured() {
  return strlen(RAW_TOKEN) > 8 && strncmp(RAW_TOKEN, "raw-collector", 13) != 0;
}
// Ship the accumulated raw TX/RX lines to the collector on the server (over WG). Clears
// the buffer only on success so a dropout doesn't lose lines (bounded by the 28 KB cap).
static void rawFlush() {
  if (!wgUp || WiFi.status() != WL_CONNECTED || rawBuf.length() == 0) return;
  HTTPClient http;
  http.setConnectTimeout(2000);
  http.setTimeout(3000);
  if (!http.begin(RAW_URL)) return;
  http.addHeader("X-Token", RAW_TOKEN);
  http.addHeader("Content-Type", "text/plain");
  lastRawCode = http.POST(rawBuf);
  http.end();
  if (lastRawCode == 204 || lastRawCode == 200) rawBuf = "";
}
// Append `key=value` to an Influx line-protocol field set (comma-separated).
static void appendField(String &line, bool &first, const char *key, float v) {
  char b[24]; snprintf(b, sizeof b, "%.3f", v);
  if (!first) line += ",";
  first = false;
  line += key; line += "="; line += b;
}

// Read the curated LIDs, decode, and POST one `engine` line. Returns false if the
// session looks dead (rpm LID unreadable) so the caller re-establishes.
static bool logCycle() {
  uint8_t buf[NLIDS][80];
  int     len[NLIDS];
  bool    anyOk = false;
  for (size_t i = 0; i < NLIDS; i++) {
    len[i] = td5ReadLid(LIDS[i], buf[i], sizeof buf[i]);
    if (len[i] >= 0) anyOk = true;
    server.handleClient();   // keep the web UI responsive during the ~300 ms read burst
  }
  if (!anyOk) return false;                    // whole session gone

  // Plausibility gate: LID 09 (rpm) must read and be sane. Guards against a stray
  // establish on bench noise slipping through and logging garbage. rpm=0 is valid
  // (ignition on, engine off / KOEO), so gate on range, not presence of revs.
  int ri = -1;
  for (size_t i = 0; i < NLIDS; i++) if (LIDS[i] == 0x09) { ri = (int)i; break; }
  if (ri < 0 || len[ri] < 2) return false;
  int rpm = (buf[ri][0] << 8) | buf[ri][1];
  if (rpm < 0 || rpm > 6000) return false;

  // Coverage sweep: read ONE extra unmapped LID per cycle (round-robin). Its raw TX/RX
  // is captured for RE via kwpRequest; we don't decode it. Only when raw capture is on.
  if (rawOn) {
    static size_t sweepIdx = 0;
    uint8_t sbuf[80];
    td5ReadLid(SWEEP[sweepIdx], sbuf, sizeof sbuf);
    sweepIdx = (sweepIdx + 1) % NSWEEP;
  }

  String line = String("engine,vehicle=") + LOG_VEHICLE + " ";
  bool first = true;
  float injMg = NAN, speedKmh = NAN;
  for (const Field &f : FIELDS) {
    int li = -1;
    for (size_t i = 0; i < NLIDS; i++) if (LIDS[i] == f.lid) { li = (int)i; break; }
    if (li < 0 || len[li] < 0) continue;
    float v = decodeField(f, buf[li], len[li]);
    if (isnan(v)) continue;
    if (!strcmp(f.key, "inj_mg")) injMg = v;
    else if (!strcmp(f.key, "speed")) speedKmh = v;
    appendField(line, first, f.key, v);
  }

  // Fuel computer — derived at the source. L/h = inj[mg] * INJ_PER_REV * rpm * 60 / 1e6 /
  // (density g/mL); economy L/100km = rate/speed*100 when moving; trip integrates over time.
  // Same math + generated constants as Python _FuelComputer (signals_td5.h).
  float rate = NAN;
  if (!isnan(injMg) && rpm > 0)
    rate = injMg * INJ_PER_REV * (float)rpm * 60.0f / 1e6f / (DIESEL_G_PER_L / 1000.0f);
  uint32_t nowMs = millis();
  if (lastFuelMs != 0 && !isnan(rate)) {
    uint32_t dtms = nowMs - lastFuelMs;
    if (dtms > 3000) dtms = 3000;               // cap 3 s → no spike after a pause/reconnect
    float dt_h = dtms / 3600000.0f;
    tripFuel += (double)rate * dt_h;
    if (!isnan(speedKmh) && speedKmh > 0) tripDist += (double)speedKmh * dt_h;
  }
  lastFuelMs = nowMs;
  if (!isnan(rate)) {
    appendField(line, first, "fuel_rate", rate);                        // L/h
    if (!isnan(speedKmh) && speedKmh > 5.0f)
      appendField(line, first, "economy", rate / speedKmh * 100.0f);    // L/100km (moving)
  }
  if (tripDist > 0.1) appendField(line, first, "trip_economy", (float)(tripFuel / tripDist * 100.0));

  if (first) return true;                       // reads ok but nothing decoded — keep session
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  lastPost = influxPost(line);
  if (lastPost == 204) pointsSent++;
  return true;
}
// Node health heartbeat — proves the Influx pipe even with no car attached.
static void nodeHeartbeat() {
  String line = String("node,vehicle=") + LOG_VEHICLE +
                " rssi=" + String(WiFi.RSSI()) +
                ",uptime=" + String((millis() - bootMs) / 1000) +
                ",wg=" + String(wgUp ? 1 : 0) +
                ",session=" + String(sessionUp ? 1 : 0) +
                ",points=" + String(pointsSent);
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  influxPost(line);
}
static const uint32_t RAW_FLUSH_MS = 3000;      // ship raw batches every ~3 s
static void logTick() {
  uint32_t now = millis();
  if (now - lastBeat > BEAT_INTERVAL_MS) { lastBeat = now; nodeHeartbeat(); }
  if (rawOn && now - lastRawFlush > RAW_FLUSH_MS) { lastRawFlush = now; rawFlush(); }
  if (now - lastCycle < LOG_INTERVAL_MS) return;
  lastCycle = now;
  if (!sessionUp) {
    if (now < quietUntil) return;                 // stay OFF the bus — silence clears a stale link
    if (linkMaybeOpen) {                           // tear a leftover link down ONCE, then wait
      stopComm();
      linkMaybeOpen = false;
      quietUntil = now + ESTAB_QUIET_MS;           // ...and now SILENCE so the module times it out
      return;
    }
    sessionUp = td5Establish();                    // clean init after the quiet window (sends no 82)
    if (!sessionUp) { estabFails++; quietUntil = millis() + ESTAB_QUIET_MS; }  // quiet, then retry
    return;
  }
  if (!logCycle()) {                               // lost session (engine off?) — WE had a link:
    stopComm();                                    // tear it down once, then go quiet before retry
    sessionUp = false;
    quietUntil = millis() + ESTAB_QUIET_MS;
    lastFuelMs = 0;                                // pause fuel integration across the gap
  }
}

// Bring up the WireGuard tunnel so the node has a fixed WG IP. The handshake needs
// valid wall-clock time → NTP first. Skipped if WG_PRIVATE_KEY is the placeholder.
static void wgStart() {
  if (strlen(WG_PRIVATE_KEY) < 40) { Serial.println("WG: no key set — skipping"); return; }
  Serial.println("WG: syncing time (NTP) ...");
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  uint32_t t0 = millis();
  while (time(nullptr) < 1700000000 && millis() - t0 < 8000) delay(200);
  if (time(nullptr) < 1700000000) { Serial.println("WG: NTP failed — skipping"); return; }
  IPAddress ip; ip.fromString(WG_LOCAL_IP);
  Serial.printf("WG: connecting, local %s ...\n", WG_LOCAL_IP);
  wgUp = wg.begin(ip, WG_PRIVATE_KEY, WG_ENDPOINT, WG_PEER_PUBKEY, (uint16_t)WG_PORT);
  Serial.printf("WG: %s\n", wgUp ? "tunnel up" : "begin() failed");
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
    "a.btn{display:inline-block;margin:14px 8px 0 0;padding:12px 18px;background:#1e6feb;color:#fff;"
    "border-radius:10px;text-decoration:none;font-weight:600}</style>"
    "<h1>K-line node</h1><ul>"
    "<li>WiFi: <code>" + (ssid.length()?ssid:String("(disconnected)")) + "</code></li>"
    "<li>IP: <code>" + WiFi.localIP().toString() + "</code></li>"
    "<li>RSSI: <code>" + String(WiFi.RSSI()) + " dBm</code></li>"
    "<li>Uptime: <code>" + uptimeStr() + "</code></li>"
    "<li>WG: <code>" + (wgUp ? String(WG_LOCAL_IP) + " (up)" : String("off")) + "</code></li>"
    "<li>Logging: <code>" + (logEnabled ? String("on") : String("off")) +
      "</code> · session <code>" + (sessionUp ? "up" : "down") +
      "</code> · points <code>" + String(pointsSent) +
      "</code> · last POST <code>" + String(lastPost) + "</code></li></ul>"
    "<a class=btn href='/scan'>Test car (TD5 + SLABS)</a>"
    "<a class=btn href='/log?on=" + (logEnabled ? "0" : "1") + "'>" +
      (logEnabled ? "Stop logging" : "Start logging") + "</a>"
    "<p style='color:#888;font-size:13px'>Ignition on, node wired to OBD (K/12V/GND + 1k pull-up). "
    "Logs to InfluxDB <code>" + INFLUX_BUCKET + "</code> at <code>" + INFLUX_URL + "</code>.</p>";
  server.send(200, "text/html", html);
}
static void handleStatus() {
  server.send(200, "application/json",
    "{\"ssid\":\"" + WiFi.SSID() + "\",\"ip\":\"" + WiFi.localIP().toString() +
    "\",\"rssi\":" + String(WiFi.RSSI()) +
    ",\"uptime_s\":" + String((millis()-bootMs)/1000) +
    ",\"wg\":" + String(wgUp ? 1 : 0) +
    ",\"logging\":" + String(logEnabled ? 1 : 0) +
    ",\"session\":" + String(sessionUp ? 1 : 0) +
    ",\"points\":" + String(pointsSent) +
    ",\"estab_fails\":" + String(estabFails) +
    ",\"last_post\":" + String(lastPost) +
    ",\"raw\":" + String(rawOn ? 1 : 0) +
    ",\"rawq\":" + String(rawBuf.length()) +
    ",\"raw_post\":" + String(lastRawCode) + "}");
}
static void handleScan() {
  // Pause logging around the manual scan so the two don't fight over the bus.
  bool was = logEnabled; logEnabled = false; sessionUp = false;
  String out = kwpStartComm(0x13, "TD5") + "\n" + kwpStartComm(0x29, "SLABS") + "\n";
  logEnabled = was;
  // /scan hit the bus (its own inits); make the logger re-clear + settle before it reconnects.
  linkMaybeOpen = true; quietUntil = millis() + ESTAB_QUIET_MS;
  server.send(200, "text/plain", out);
}
static void handleLog() {
  if (server.hasArg("on")) {
    logEnabled = server.arg("on") != "0";
    if (!logEnabled) sessionUp = false;
    quietUntil = 0; linkMaybeOpen = true;       // re-clear + establish promptly when turned on
  }
  server.send(200, "application/json",
    "{\"logging\":" + String(logEnabled ? 1 : 0) + "}");
}

void setup() {
  Serial.begin(115200); delay(300); bootMs = millis();
  Serial.println("\n== K-line node: WiFi + OTA + web + K-line + Influx ==");
  WiFi.mode(WIFI_STA); WiFi.setHostname(OTA_HOSTNAME); WiFi.setAutoReconnect(true);
  wifiConnect();
  wgStart();                                 // fixed WG IP, reachable via the tunnel

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  // Suspend K-line/logging while an OTA image is uploading — a mid-flash bus read
  // would only steal cycles from the write.
  ArduinoOTA.onStart([]() { logEnabled = false; sessionUp = false; });
  ArduinoOTA.begin();                       // also starts mDNS as OTA_HOSTNAME
  MDNS.addService("http", "tcp", 80);       // advertise the web server (shows up in Fing/Bonjour)

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.on("/scan", handleScan);
  server.on("/log", handleLog);
  server.begin();

  logEnabled = influxConfigured();          // auto-start logging if a token is set
  rawOn = rawConfigured();                   // raw TX/RX streaming if a collector token is set
  rawBuf.reserve(30000);                     // avoid heap fragmentation from repeated growth
  klineRawTap = rawCapture;                  // let the comms core feed raw TX/RX to the logger
  Serial.printf("Web http://%s/  · /scan tests the car · logging %s · raw %s · OTA '%s'.\n",
                WiFi.localIP().toString().c_str(), logEnabled ? "ON" : "off",
                rawOn ? "ON" : "off", OTA_HOSTNAME);
}

static uint32_t lastWifiCheck = 0;
static uint32_t lastKeepalive = 0;
static uint32_t lastWgTry = 0;
void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiCheck > 10000) {
    lastWifiCheck = millis();
    Serial.println("WiFi: link down, reconnecting ...");
    wifiConnect();
  }
  // WG can miss at boot if NTP was slow over the hotspot's CGNAT. Retry while WiFi is
  // up so the tunnel (and thus Influx logging to 10.9.0.1) recovers without a reboot.
  if (!wgUp && WiFi.status() == WL_CONNECTED && millis() - lastWgTry > 30000) {
    lastWgTry = millis();
    wgStart();
  }
  // WG persistent keepalive: the lib has none, and the node sits behind the hotspot's
  // NAT — send a tiny packet into the tunnel every 20 s so the mapping stays open and
  // the server can reach us at 10.9.0.9 even when idle.
  if (wgUp && millis() - lastKeepalive > 20000) {
    lastKeepalive = millis();
    kaUdp.beginPacket(IPAddress(10, 9, 0, 1), 51820);  // any WG-net IP → routes via wg → NAT refresh
    kaUdp.write((uint8_t)0);
    kaUdp.endPacket();
  }
  if (logEnabled) logTick();
}
