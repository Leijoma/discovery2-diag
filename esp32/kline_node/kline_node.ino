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

// ---------------- LID decode table ----------------
// Defined up here (before any function) so Arduino's auto-generated prototypes see them.
enum Kind { U8, U16, S16 };
struct Field { const char *key; uint8_t lid; uint8_t off; uint8_t kind; float scale; float bias; };
// FIELDS[]/LIDS[]/NLIDS are GENERATED from src/d2diag/signals/td5.json — one source of
// truth for both platforms. Regenerate with: python3 tools/gen_signal_header.py
#include "signals_td5.h"
// Coverage sweep: unmapped LIDs the reference tool polls (fuelling/switch blocks). Read
// ONE per cycle, round-robin — raw-captured for RE, not decoded. Mirrors _TD5_COVERAGE_EXTRA.
static const uint8_t SWEEP[] = { 0x1E, 0x1F, 0x20, 0x36 };
static const size_t  NSWEEP  = sizeof SWEEP / sizeof SWEEP[0];

// ---------------- K-line ----------------
static const int      PIN_KRX      = 16;      // L9637D pin 1 (RX) -> GPIO16
static const int      PIN_KTX      = 17;      // GPIO17 -> L9637D pin 4 (TX)
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = false;   // L9637D is non-inverting
static const uint8_t  TESTER_ADDR  = 0xF7;
static const uint8_t  TD5_ADDR     = 0x13;

static uint8_t checksum(const uint8_t *d, size_t n) {
  uint16_t s = 0; for (size_t i = 0; i < n; i++) s += d[i]; return (uint8_t)(s & 0xFF);
}
static String toHex(const uint8_t *d, size_t n) {
  String s; char b[4];
  for (size_t i = 0; i < n; i++) { snprintf(b, sizeof b, "%02X ", d[i]); s += b; }
  s.trim(); return s;
}
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
static size_t readBytes(uint8_t *buf, size_t n, uint32_t timeout_ms) {
  size_t got = 0; uint32_t t0 = millis();
  while (got < n && millis() - t0 < timeout_ms)
    while (Serial2.available() && got < n) buf[got++] = (uint8_t)Serial2.read();
  return got;
}
// Read a reply burst: collect bytes until `gap` ms of silence after the first byte, or
// `overall` ms total. The KKL/L9637D echo lands on the same line, so the burst holds our
// echo + the ECU reply (+ occasional glitch); callers search it for the response SID.
static size_t readBurst(uint8_t *buf, size_t cap, uint32_t overall, uint32_t gap) {
  size_t got = 0; uint32_t t0 = millis(); uint32_t last = t0;
  while (millis() - t0 < overall) {
    if (Serial2.available()) {
      uint8_t b = (uint8_t)Serial2.read();
      if (got < cap) buf[got++] = b;
      last = millis();
    } else if (got > 0 && millis() - last > gap) {
      break;
    }
  }
  return got;
}
static int findSeq(const uint8_t *buf, size_t n, uint8_t a, uint8_t b) {
  for (size_t i = 0; i + 1 < n; i++) if (buf[i] == a && buf[i + 1] == b) return (int)i;
  return -1;
}
static int findByte(const uint8_t *buf, size_t n, uint8_t a) {
  for (size_t i = 0; i < n; i++) if (buf[i] == a) return (int)i;
  return -1;
}
static bool serial2Up = false;                 // is Serial2 begun? stopComm needs it
static void ensureSerial() {
  if (!serial2Up) {
    Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
    serial2Up = true;
  }
}
// StopCommunication (82 → C2): tear down any link left open on the shared bus. A
// 7F 81 10 (generalReject) on the next StartCommunication means a link is STILL open,
// so we send this before every init AND whenever we abandon a session. Wait out the
// C2 (or timeout) so the module has actually processed the teardown before we move on —
// a bare write + 30 ms was too quick and left links open (proven in the car 2026-08-24).
static void stopComm() {
  ensureSerial();
  uint8_t s[3] = { 0x01, 0x82, 0x83 };
  while (Serial2.available()) Serial2.read();
  Serial2.write(s, 3); Serial2.flush();
  uint8_t tmp[16];
  readBurst(tmp, sizeof tmp, 120, 30);         // absorb C2 / let the link close
  while (Serial2.available()) Serial2.read();
}
static void klineFastInit() {                  // ISO 14230-2 fast init
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(300);   // W5 idle
  digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW); delay(25);    // 25 ms low
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(25);    // 25 ms high
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
  serial2Up = true;
}

// Unaddressed KWP2000 request (`<len> <SID> <payload…> <cs>`), tolerant read. On a
// positive reply (SID|0x40) copies the data field (echoed id + data, NO checksum) to
// `out` and returns its length; returns -1 on a negative response or no reply. The
// length byte just before the response SID bounds the field precisely, dodging the
// trailing checksum and any turnaround glitch.
static int kwpRequest(uint8_t sid, const uint8_t *payload, size_t plen,
                      uint8_t *out, size_t outCap) {
  uint8_t req[16]; size_t n = 0;
  req[n++] = (uint8_t)(1 + plen);            // length: SID + payload
  req[n++] = sid;
  for (size_t i = 0; i < plen; i++) req[n++] = payload[i];
  req[n] = checksum(req, n); n++;
  while (Serial2.available()) Serial2.read();
  rawCapture("TX", req, n);
  Serial2.write(req, n); Serial2.flush();

  uint8_t burst[96];
  size_t got = readBurst(burst, sizeof burst, 250, 30);
  rawCapture("RX", burst, got);
  uint8_t pos = sid | 0x40;
  int idx = -1;
  if (plen > 0) idx = findSeq(burst, got, pos, payload[0]);   // e.g. 61 <lid>, 67 <level>
  if (idx < 0) idx = findByte(burst, got, pos);              // e.g. 50 (no echoed sub)
  int neg = findSeq(burst, got, 0x7F, sid);
  if (idx >= 1 && (neg < 0 || idx <= neg)) {
    uint8_t lenb = burst[idx - 1];                           // response length (incl SID)
    size_t after = (lenb >= 1) ? (size_t)(lenb - 1) : 0;     // bytes after the SID
    if ((size_t)idx + 1 + after > got) after = got - (idx + 1);
    if (after > outCap) after = outCap;
    memcpy(out, burst + idx + 1, after);
    return (int)after;
  }
  return -1;
}

// Td5 SecurityAccess seed→key (LFSR variant). Ported from td5keygen (BSD-2-Clause);
// see src/d2diag/td5/keygen.py and THIRD_PARTY_LICENSES.md.
static uint16_t td5KeyFromSeed(uint16_t seed) {
  int count = ((seed >> 0xC) & 0x8) | ((seed >> 0x5) & 0x4)
            | ((seed >> 0x3) & 0x2) | (seed & 0x1);
  count += 1;
  for (int i = 0; i < count; i++) {
    uint16_t tap = ((seed >> 1) ^ (seed >> 2) ^ (seed >> 8) ^ (seed >> 9)) & 1;
    uint16_t tmp = (uint16_t)(((seed >> 1) | (tap << 0xF)) & 0xFFFF);
    if (((seed >> 0x3) & 1) && ((seed >> 0xD) & 1)) seed = (uint16_t)(tmp & ~1);
    else                                            seed = (uint16_t)(tmp | 1);
  }
  return seed;
}

// Full Td5 bring-up to an unlocked, readable session. Returns true on success.
static bool td5Establish() {
  stopComm();
  klineFastInit();
  // StartCommunication (addressed 81 13 F7 81) → expect C1 in the burst.
  uint8_t req[5] = { 0x81, TD5_ADDR, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);
  while (Serial2.available()) Serial2.read();
  rawCapture("TX", req, 5);
  Serial2.write(req, 5); Serial2.flush();
  uint8_t burst[32];
  size_t got = readBurst(burst, sizeof burst, 500, 40);
  rawCapture("RX", burst, got);
  // Require the real StartCommunication key bytes (C1 57 8F), not just any 0xC1. A
  // floating K-line on the bench otherwise false-positives on noise and logs garbage;
  // both Td5 and SLABS answer 57 8F, so this is exact for the car.
  // On every failure after fast init, tear the link down (stopComm) before returning —
  // a half-opened link left behind is exactly what makes the NEXT StartCommunication get
  // 7F 81 10 (generalReject), which then never self-clears.
  int ci = findSeq(burst, got, 0xC1, 0x57);
  if (ci < 0 || ci + 2 >= (int)got || burst[ci + 2] != 0x8F) { stopComm(); return false; }

  uint8_t out[64];
  // StartDiagnosticSession 0xA0 → positive 0x50.
  uint8_t sub = 0xA0;
  if (kwpRequest(0x10, &sub, 1, out, sizeof out) < 0) { Serial.println("EST: session fail"); stopComm(); return false; }
  // SecurityAccess: request seed (level 01) → data = [echoed level, seed_hi, seed_lo].
  uint8_t lvl1 = 0x01;
  int r = kwpRequest(0x27, &lvl1, 1, out, sizeof out);
  if (r < 3) { Serial.println("EST: seed fail"); stopComm(); return false; }
  uint16_t seed = (uint16_t)((out[1] << 8) | out[2]);
  uint16_t key = td5KeyFromSeed(seed);
  // Send key (level 02).
  uint8_t kp[3] = { 0x02, (uint8_t)(key >> 8), (uint8_t)(key & 0xFF) };
  if (kwpRequest(0x27, kp, 3, out, sizeof out) < 0) { Serial.println("EST: key fail"); stopComm(); return false; }
  return true;
}

// Read one LID (21 xx). Copies the DATA field (after the echoed id) to `data`,
// returns its length, or -1 on failure.
static int td5ReadLid(uint8_t lid, uint8_t *data, size_t cap) {
  uint8_t out[80];
  int r = kwpRequest(0x21, &lid, 1, out, sizeof out);
  if (r < 1) return -1;                        // out[0] is the echoed lid
  size_t len = (size_t)(r - 1);
  if (len > cap) len = cap;
  memcpy(data, out + 1, len);
  return (int)len;
}

// One module StartCommunication for the /scan diagnostic page.
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

static float decodeField(const Field &f, const uint8_t *d, int len) {
  int need = (f.kind == U8) ? 1 : 2;
  if (f.off + need > len) return NAN;
  long raw;
  if (f.kind == U8)  raw = d[f.off];
  else {
    uint16_t u = (uint16_t)((d[f.off] << 8) | d[f.off + 1]);   // big-endian
    raw = (f.kind == S16) ? (int16_t)u : u;
  }
  return raw * f.scale + f.bias;
}

// ---------------- InfluxDB logging ----------------
static bool     sessionUp    = false;
static uint32_t lastCycle    = 0;
static uint32_t lastEstab    = 0;
static uint32_t lastBeat     = 0;
static int      lastPost     = 0;      // last engine POST HTTP code (0 = none yet)
static uint32_t pointsSent   = 0;
static uint32_t estabFails   = 0;
static const uint32_t LOG_INTERVAL_MS   = 1000;
static const uint32_t ESTAB_BACKOFF_MS  = 5000;   // retry a dead session at most this often
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
  for (const Field &f : FIELDS) {
    int li = -1;
    for (size_t i = 0; i < NLIDS; i++) if (LIDS[i] == f.lid) { li = (int)i; break; }
    if (li < 0 || len[li] < 0) continue;
    float v = decodeField(f, buf[li], len[li]);
    if (isnan(v)) continue;
    char b[24]; snprintf(b, sizeof b, "%.3f", v);
    if (!first) line += ",";
    first = false;
    line += f.key; line += "="; line += b;
  }
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
    if (now - lastEstab < ESTAB_BACKOFF_MS) return;
    lastEstab = now;
    sessionUp = td5Establish();                 // ~0.5 s; brief web/OTA pause is fine
    if (!sessionUp) estabFails++;
    return;
  }
  if (!logCycle()) { stopComm(); sessionUp = false; }  // lost session (engine off?) →
                                                       // close our link so the next
                                                       // establish isn't generalReject'd
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
  server.send(200, "text/plain", out);
}
static void handleLog() {
  if (server.hasArg("on")) {
    logEnabled = server.arg("on") != "0";
    if (!logEnabled) sessionUp = false;
    lastEstab = 0;                              // allow an immediate (re)establish
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
