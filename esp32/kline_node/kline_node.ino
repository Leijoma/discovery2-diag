// kline_node.ino — ESP32 K-line node: WiFi + OTA + web + K-line + InfluxDB logging.
//
// Standalone node firmware. ESP32 Arduino core only.
//   - WiFi: multi-network with PRIORITY — WIFI_SSID_1 (home), then WIFI_SSID_CAR (the
//     Pi's own AP, discopi), then WIFI_SSID_2 (phone hotspot). Non-blocking roaming: it
//     keeps scanning and moves up when a better network appears (see wifiTick()).
//   - OTA: after the first USB flash, later flashes go over WiFi (password-gated).
//   - WireGuard: fixed tunnel IP so the node is reachable from the phone regardless
//     of the hotspot DHCP address (see hardware/README.md).
//   - Web: status page + /status JSON + /scan (fast init + StartCommunication) + /log + /bridge.
//   - USB CABLE MODE: the same firmware doubles as a K-line cable. A host tool (Python
//     EspTransport) sending PING/INIT/TX/STOP over USB takes the shared bus; the node
//     suspends logging, relays raw bytes (fast-init pulse done locally), and resumes
//     logging when USB goes quiet. So there is ONE firmware — logging and cable are two
//     runtime roles, selectable from the web (/bridge) or automatic on a USB command.
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
#include <LittleFS.h>            // on-device spill for offline logging (store-and-forward)
#include <Preferences.h>         // NVS — persist slabs_poll across reboots
#include <lwip/netif.h>         // re-assert the WG netif as default route after a roam
#include <esp_system.h>          // esp_reset_reason() — why did we boot? (brownout/panic/wdt)
#include "secrets.h"
#include "kline_core.h"          // K-line/KWP2000/Td5 comms core (no WiFi/Influx/web)
#include "live_html.h"           // the live web UI (embedded page; own header, see note there)

static WebServer server(80);
static Preferences prefs;              // NVS store for persisted settings (slabs_poll)
static WireGuard wg;
static bool wgUp = false;
// WiFi roaming state lives in the WiFi section; these two are needed earlier (uplink choice).
static const int WIFI_CAR = 1;                 // NETS index of the Pi's AP (Discopi)
static int wifiCur = -1;                       // NETS index we're on, -1 = none
// On the Pi's AP, Influx lines go to the Pi's store-and-forward relay instead of over WG
// to the home server: the Pi keeps them on disk and forwards when it has an uplink. Same
// /api/v2/write API, so only the base URL changes. NTP comes from the Pi too (GPS time).
#ifndef RELAY_URL
#define RELAY_URL "http://192.168.4.1:8086"
#endif
#ifndef CAR_NTP
#define CAR_NTP "192.168.4.1"
#endif
static bool onCarNet() { return wifiCur == WIFI_CAR && WiFi.status() == WL_CONNECTED; }
// Can a POST to Influx (or the relay) get anywhere right now?
static bool uplinkReady() {
  if (WiFi.status() != WL_CONNECTED) return false;
  return onCarNet() || wgUp;                   // off the car net, 10.9.0.1 is only reachable over WG
}
// configTime() restarts SNTP and its first request goes out only after a startup delay,
// so calling it again on every network change / WG retry kept resetting it before it
// answered (first boot with the roaming code: "NTP failed"). Reconfigure only when the
// server set actually changes.
static int ntpMode = -1;                       // -1 never · 0 internet · 1 car (Pi first)
static void ntpStart() {
  int m = onCarNet() ? 1 : 0;
  if (m == ntpMode) return;
  ntpMode = m;
  if (m) configTime(0, 0, CAR_NTP, "pool.ntp.org", "time.nist.gov");
  else   configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}
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
static uint32_t tripStartMs  = 0;      // first integration tick of this trip (0 = no trip yet)
// Latest decoded snapshot as JSON — drives the local /live page (and later an on-device
// screen). Updated each cycle in logCycle; read by the web handlers. All on the loop, so
// no locking needed.
static String   latestJson;            // {"rpm":763,...}
static uint32_t latestMs = 0;          // millis() of the last snapshot
// Demo mode (/demo?on=1): synthetic drive data for testing a UI without the car. RAM only, so
// a reboot always returns to real logging. It stays off K-line entirely and tags its points
// vehicle=demo, so they never mix with the real vehicle's series in Influx.
static bool     demoMode = false;
static String   faultsHex;             // raw 21 3B fault block (hex) — browser decodes via faultmap.json
static uint8_t  faultTick = 0;         // counter: read the fault block ~every 10th cycle
static uint8_t  prevFaults[35];        // last fault block, for edge detection (onset/clear events)
static bool     haveFaultBase = false; // seen the first block this session? (don't emit pre-existing as new)
static int      nFaults = 0;           // active fault bits right now (logged to Influx each cycle)
// Stale-link recovery: a link left open (dropped session / prior run) makes the ECU answer
// 7F 81 10 to every StartCommunication. On RDL016 (2026-08-27) bus SILENCE does NOT clear it
// (25 s + ESP reboot both failed) — only an accepted StopCommunication (82) or an ignition
// cycle does. So td5Establish() sends 82 before EVERY attempt (like the KKL stack), and if the
// ECU still rejects after IGN_HINT_AFTER tries we surface an ignition-cycle prompt in the UI.
static uint32_t quietUntil    = 0;     // don't touch K-line before this (ms)
static bool     recoveryCleared = false; // teardown (endSession) sent for this recovery episode?
static bool     needIgnCycle  = false; // establish keeps failing → teardown+silence not clearing it, cycle the key
static uint8_t  sessionMiss  = 0;      // consecutive failed read cycles while a session is up
static uint16_t estabTries   = 0;      // consecutive establish failures since the last success
static const uint32_t LOG_INTERVAL_MS   = 1000;
static const uint32_t ESTAB_QUIET_MS    = 6000;   // settle window after /scan hit the bus
static const uint32_t RECOVERY_IDLE_MS  = 6000;   // base bus-silent window after a teardown (escalates)
static const uint32_t RECOVERY_IDLE_MAX = 25000;  // ...up to this (the KKL stack idles ~25 s; car-proven)
static const uint8_t  SESSION_MISS_GRACE  = 3;    // tolerate this many glitchy reads before dropping a session
static const uint16_t IGN_HINT_AFTER    = 4;      // establish fails in a row → prompt an ignition cycle
// KL15 power = power-on IS ignition-on, so hold off K-line for the first few seconds to clear
// the crank / BCU<->ECM immobiliser handshake window. Hardware-free (a timed floor, not a
// measurement); harmless on USB/constant-12V too. WiFi/WG bring-up usually covers this already,
// but this guarantees it even if no network was found and setup returned fast.
static const uint32_t BOOT_QUIET_MS     = 5000;   // don't touch the bus in the first 5 s after boot
static const uint32_t BEAT_INTERVAL_MS  = 15000;  // node heartbeat cadence

// Sparse SLABS excursion (opt-in via /slabs): every SLABS_INTERVAL_MS the node briefly leaves the
// TD5 session, reads a few SLABS LIDs, logs them + whether SLABS answered at the current speed
// (to find where SLABS diagnostics drop out), then returns to TD5. Pauses live TD5 data ~2-3 s.
static bool     slabsPoll   = false;   // toggled from Settings
static uint32_t lastSlabs   = 0;
static String   slabsFlog, slabsFcur;  // raw SLABS fault blocks (logged 21 11 / current 21 47) for /live
static float    lastSpeedKmh = NAN;    // last decoded TD5 speed — gates + labels the SLABS sample
// SLABS diagnostics answer ONLY at a standstill (proven RDL016 2026-08-29: silent — StartComm just
// echoes, no reply — once moving, and stays dead until an ignition cycle). So only excurse when
// stopped, and then sample a bit more often (SLABS is up, so it succeeds on the first try).
static const uint32_t SLABS_STILL_MS  = 60000;    // sample this often while stationary (60 s: logged
                                                  // faults/heights change slowly; the ~10 s cadence
                                                  // visibly blinked the dash each excursion — RDL016)
static const float    SLABS_STILL_KMH = 5.0f;     // "stationary" threshold
static const uint32_t SLABS_SETTLE_MS = 900;      // bus-silent gap after TD5 teardown before SLABS init
// Read-and-clear at start (B-011 in ../Discovery 2/02-backlog.md). The intermittent "amigos" clear
// at every ignition cycle, but they LATCH into the logged block 21 11, which has read the same
// 020 + 027 since 2026-08 because it was never cleared. Clearing it once per ignition cycle makes
// each start's 21 11 read show exactly what the PREVIOUS drive logged (020 alone = 3 lamps, 027 =
// 4 lamps). Never erases what isn't stored: the pre-clear block must reach Influx (204) first.
// ⚠ A workshop will then only see the last drive, and the per-code counters are lost.
static bool     slabsClear       = true;   // persisted ("sclear"); /slabsclear
static bool     slabsClearedBoot = false;  // cleared in THIS ignition cycle (node power = KL15)
static uint8_t  slabsClearTries  = 0;      // clear attempts this cycle (capped, see slabsExcursion)

// SLABS HOLD (fault-order test, references/test_plan.md T-23). The excursions above prove only that
// SLABS refuses a NEW StartCommunication once the car has moved — so its CURRENT faults (21 47), the
// "four amigos" that vanish at the next ignition cycle, have never been read while lit. Hold mode
// drops TD5 logging entirely and keeps ONE SLABS session, opened at a standstill, alive through the
// drive, logging every fault bit edge with a poll counter so the ORDER of onsets can be read back.
// Load: one request per second (the session-killer was ~10 req/s — slabs_protocol.md), cycling
// HOLD_PATTERN: 0 = 21 47 current faults, 1 = bare 3E keepalive, 2 = 21 43 wheel speeds / 21 11.
static bool     slabsHold     = false;  // mode switch (persisted in NVS; /slabshold)
static bool     holdUp        = false;  // a hold-mode SLABS session is currently established
static uint32_t holdSince     = 0;      // millis() the current hold session came up
static uint32_t holdLastTick  = 0;
static uint32_t holdNextTry   = 0;      // next establish attempt (millis)
static uint32_t holdSeq       = 0;      // 21 47 poll counter — orders events sharing a 1 s timestamp
static uint32_t holdLostAfterS = 0;     // how long the last hold session survived before dying (s)
static uint8_t  holdStep      = 0;
static uint8_t  holdMiss      = 0;      // consecutive unanswered requests
static uint8_t  holdWheelN    = 0;      // wheel-slot counter (every 8th slot reads 21 11 instead)
static uint8_t  holdCur[16], holdLog[16];
static bool     holdHaveCur   = false, holdHaveLog = false;
static String   holdW43;                // last raw 21 43 (decoding belagt; scale + wheel order kandidat)
static const uint8_t  HOLD_PATTERN[]  = { 0, 1, 0, 2 };  // current faults every 2 s; 3E + wheels every 4 s
static const uint32_t HOLD_TICK_MS    = 1000;
static const uint32_t HOLD_RETRY_MS   = 20000;  // retry establish this often after a loss / failed init
static const uint8_t  HOLD_MISS_MAX   = 3;      // unanswered requests in a row → the session is gone

// USB serial bridge (ESP-as-cable). One firmware, two roles: normally the node LOGS
// autonomously; when a host tool (Python EspTransport, KKL-compatible line protocol)
// sends a command over USB, the node hands it the shared K-line bus. K-line is a single-
// master half-duplex bus, so the roles can't drive it at once — but they switch at runtime
// (auto on a USB command, or via /bridge), and the node resumes logging BRIDGE_IDLE_MS
// after the last USB command. Frees the KKL cable: plug the ESP into the Mac, run the
// whole Python stack over it like the cable, then it goes back to logging on its own.
static bool     bridgeMode      = false;
static bool     bridgeSticky    = false;          // set via /bridge (web) — hold until explicitly left
static uint32_t bridgeIdleUntil = 0;
static const uint32_t BRIDGE_IDLE_MS = 30000;     // AUTO (USB) mode: resume logging this long after the last command

// Offline logging (store-and-forward): when an engine POST fails (no WG/Influx), spill the
// line to LittleFS and flush it back when the uplink returns — so a drive out of hotspot
// range isn't lost. Each spilled line already carries its epoch timestamp, so it lands at
// the right time; and Influx overwrites points with the same tag+timestamp, so re-sending
// after a reboot is idempotent (we track the read offset in RAM only).
static const char*    SPILL_PATH   = "/spill.lp";
static const uint32_t SPILL_MAX    = 1000000;   // ~1 MB cap (~1–2 h) → drop newest when full
static const uint32_t SPILL_CHUNK  = 8000;      // bytes per flush POST
static const uint32_t SPILL_FLUSH_MS = 2000;
static bool     fsReady      = false;
static uint32_t spillOffset  = 0;               // bytes of SPILL_PATH already flushed (RAM)
static uint32_t spillDropped = 0;               // lines dropped because the cap was hit
static uint32_t lastSpillFlush = 0;

static bool influxConfigured() {
  return strlen(INFLUX_TOKEN) > 20 && strncmp(INFLUX_TOKEN, "influx-write", 12) != 0;
}
static int influxPost(const String &body) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  if (!uplinkReady()) return -3;               // no route to 10.9.0.1 without the tunnel
  HTTPClient http;
  String url = String(onCarNet() ? RELAY_URL : INFLUX_URL) + "/api/v2/write?org=" + INFLUX_ORG +
               "&bucket=" + INFLUX_BUCKET + "&precision=s";
  // Keep these SHORT: this POST runs on the K-line poll thread, so a slow uplink stalls
  // both live reads (rpm lag) and control clicks (mute/bridge). Fail fast → spill instead;
  // a healthy link answers in well under this, a slow one drops to the offline buffer.
  http.setConnectTimeout(800);
  http.setTimeout(1000);
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
// Append one failed engine line to the on-device spill (bounded). Newest is dropped when full
// (the oldest, flushed first, is kept — a drive's start survives; a very long gap loses the tail).
static void spillLine(const String &line) {
  if (!fsReady || epochNow() == 0) return;    // need FS + a real timestamp to be useful later
  File f = LittleFS.open(SPILL_PATH, FILE_APPEND);
  if (!f) return;
  if (f.size() < SPILL_MAX) { f.print(line); f.print('\n'); }
  else spillDropped++;
  f.close();
}
// Send a chunk of the spill backlog to Influx and advance the read offset; delete the file
// once drained. Idempotent: on reboot spillOffset resets to 0 and we re-send from the start
// (Influx overwrites same tag+timestamp points).
static void flushSpill() {
  if (!fsReady || !uplinkReady()) return;
  File f = LittleFS.open(SPILL_PATH, FILE_READ);
  if (!f) return;
  size_t sz = f.size();
  if (spillOffset >= sz) { f.close(); LittleFS.remove(SPILL_PATH); spillOffset = 0; return; }
  f.seek(spillOffset);
  String chunk; chunk.reserve(SPILL_CHUNK + 256);
  while (f.available() && chunk.length() < SPILL_CHUNK) chunk += (char)f.read();
  while (f.available()) { char c = f.read(); chunk += c; if (c == '\n') break; }  // whole lines only
  size_t consumed = f.position() - spillOffset;
  f.close();
  if (chunk.length() == 0) return;
  if (influxPost(chunk) == 204) {
    spillOffset += consumed;
    if (spillOffset >= sz) { LittleFS.remove(SPILL_PATH); spillOffset = 0; }
  }
}
static bool rawConfigured() {
  return strlen(RAW_TOKEN) > 8 && strncmp(RAW_TOKEN, "raw-collector", 13) != 0;
}
// Ship the accumulated raw TX/RX lines to the collector on the server (over WG). Clears
// the buffer only on success so a dropout doesn't lose lines (bounded by the 28 KB cap).
static void rawFlush() {
  if (!wgUp || WiFi.status() != WL_CONNECTED || rawBuf.length() == 0) return;
  HTTPClient http;
  http.setConnectTimeout(800);
  http.setTimeout(1200);
  if (!http.begin(RAW_URL)) return;
  http.addHeader("X-Token", RAW_TOKEN);
  http.addHeader("Content-Type", "text/plain");
  lastRawCode = http.POST(rawBuf);
  http.end();
  if (lastRawCode == 204 || lastRawCode == 200) rawBuf = "";
}
// Append `key=value` to an Influx line-protocol field set (comma-separated).
// Append `key=value` to the Influx line AND `"key":value` to the JSON snapshot at once.
static void appendField(String &line, String &js, bool &first, const char *key, float v) {
  char b[24]; snprintf(b, sizeof b, "%.3f", v);
  if (!first) { line += ","; js += ","; }
  first = false;
  line += key; line += "="; line += b;
  js += "\""; js += key; js += "\":"; js += b;
}

// Post a fault edge as its own timestamped Influx point (raw bit id — Grafana/analysis maps it
// to text via faultmap.json). state=1 onset, 0 cleared. Lets you overlay "when did the fault
// appear" against rpm/boost/battery in the engine series at the same timestamp.
static void postFaultEvent(int off, int bit, int state) {
  String line = String("fault,vehicle=") + LOG_VEHICLE + ",bit=" + String(off) + "." + String(bit) +
                " state=" + String(state) + "i";
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  influxPost(line);
}

// Fuel computer — derived at the source. L/h = inj[mg] * INJ_PER_REV * rpm * 60 / 1e6 /
// (density g/mL); economy L/100km = rate/speed*100 when moving; trip integrates over time.
// Same math + generated constants as Python _FuelComputer (signals_td5.h). Shared by the
// real logCycle and demoTick so the demo exercises exactly the same derived fields.
static void appendFuel(String &line, String &js, bool &first, int rpm, float injMg, float speedKmh) {
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
    appendField(line, js, first, "fuel_rate", rate);                        // L/h
    if (!isnan(speedKmh) && speedKmh > 5.0f)
      appendField(line, js, first, "economy", rate / speedKmh * 100.0f);    // L/100km (moving)
  }
  if (tripDist > 0.1) appendField(line, js, first, "trip_economy", (float)(tripFuel / tripDist * 100.0));
  // Trip totals since start (= since the node powered on with the key, or since demo on):
  // litres burnt, km driven, minutes, and average speed. Sent every cycle so a display that
  // comes up late (the Pi boots ~30 s after the node) still gets the whole trip.
  if (!isnan(rate) && tripStartMs == 0) tripStartMs = nowMs;
  if (tripStartMs) {
    float tmin = (nowMs - tripStartMs) / 60000.0f;
    appendField(line, js, first, "trip_fuel", (float)tripFuel);              // L
    appendField(line, js, first, "trip_km", (float)tripDist);                // km
    appendField(line, js, first, "trip_min", tmin);                          // minutes
    if (tmin > 0.5f) appendField(line, js, first, "trip_avg_kmh", (float)(tripDist / (tmin / 60.0f)));
  }
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

  // Fault block (21 3B): read lightly (~every 10th cycle) and stash the RAW bytes. The ESP does
  // NOT decode — the browser fetches faultmap.json from GitHub and turns these bits into text,
  // so the fault dictionary stays off the node. Trim to the 35-byte block (drop checksum glitch).
  if (++faultTick >= 10) {
    faultTick = 0;
    uint8_t fb[64];
    int fn = td5ReadLid(0x3B, fb, sizeof fb);
    // Only trust a FULL 35-byte block. A short read over the ESP relay was giving phantom bits
    // (nfaults jittering 0..9) — reject it and keep the last good block instead of logging noise.
    if (fn >= 34) {
      int n = fn > 35 ? 35 : fn;
      faultsHex = toHex(fb, n);
      int cnt = 0;
      for (int i = 0; i < n; i++) for (int b = 0; b < 8; b++) if (fb[i] & (1 << b)) cnt++;
      nFaults = cnt;
      if (haveFaultBase) {                          // emit an event for each bit that flipped
        for (int i = 0; i < n; i++) {
          uint8_t d = fb[i] ^ prevFaults[i];
          if (d) for (int b = 0; b < 8; b++) if (d & (1 << b)) postFaultEvent(i, b, (fb[i] >> b) & 1);
        }
      }
      haveFaultBase = true;
      for (int i = 0; i < n; i++) prevFaults[i] = fb[i];
    }
  }

  String line = String("engine,vehicle=") + LOG_VEHICLE + " ";
  String js = "{";
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
    appendField(line, js, first, f.key, v);
  }

  appendField(line, js, first, "nfaults", (float)nFaults);   // fault count — see fault onset in Grafana
  if (!isnan(speedKmh)) lastSpeedKmh = speedKmh;             // remember speed for the SLABS excursion

  appendFuel(line, js, first, rpm, injMg, speedKmh);

  if (first) return true;                       // reads ok but nothing decoded — keep session
  js += "}"; latestJson = js; latestMs = millis();   // publish the snapshot for /live + a screen
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  server.handleClient();                 // honour a pending mute/bridge click BEFORE the blocking POST
  lastPost = influxPost(line);
  if (lastPost == 204) pointsSent++;
  else spillLine(line);                  // offline / POST failed → buffer to LittleFS, flush later
  return true;
}
// Why did the ESP last boot? Distinguishes a crank/power brownout from a firmware panic/watchdog.
static const char *resetReasonStr() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return "poweron";
    case ESP_RST_BROWNOUT:  return "brownout";
    case ESP_RST_PANIC:     return "panic";
    case ESP_RST_TASK_WDT:  return "task_wdt";
    case ESP_RST_INT_WDT:   return "int_wdt";
    case ESP_RST_WDT:       return "wdt";
    case ESP_RST_SW:        return "sw";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    case ESP_RST_EXT:       return "ext";
    default:                return "other";
  }
}

// Node health heartbeat — proves the Influx pipe even with no car attached.
static void nodeHeartbeat() {
  String line = String("node,vehicle=") + LOG_VEHICLE +
                " rssi=" + String(WiFi.RSSI()) +
                ",uptime=" + String((millis() - bootMs) / 1000) +
                ",wg=" + String(wgUp ? 1 : 0) +
                // uplink: 0 none · 1 home · 2 car (Discopi → Pi relay) · 3 phone
                ",net=" + String(WiFi.status() == WL_CONNECTED && wifiCur >= 0 ? wifiCur == 0 ? 1 : wifiCur == WIFI_CAR ? 2 : 3 : 0) + "i" +
                ",session=" + String(sessionUp ? 1 : 0) +
                ",hold=" + String(slabsHold ? (holdUp ? 2 : 1) : 0) +   // 0 off · 1 waiting · 2 SLABS held
                ",demo=" + String(demoMode ? 1 : 0) + "i" +
                // The node's states that explain missing engine data, so a reader of the pushed
                // lines (the Pi's Car pane) needs nothing from /data. bridge=1 is only ever sent
                // once, on entering cable mode from the web: in cable mode the node doesn't beat.
                ",bridge=" + String(bridgeMode ? 1 : 0) + "i" +
                ",ign_cycle=" + String(needIgnCycle ? 1 : 0) + "i" +
                ",logging=" + String(logEnabled ? 1 : 0) + "i" +
                ",reset=\"" + resetReasonStr() + "\"" +
                ",points=" + String(pointsSent);
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  influxPost(line);
}
// Brief SLABS excursion: leave TD5, read heights/ABS-sensor-V/wheel-speeds, log them + whether
// SLABS answered at the current speed, then hand the bus back to TD5 (fast re-establish). The raw
// LID hex is logged for offline decode; `reachable` + `speed` are numbers so Grafana can show at
// what speed SLABS diagnostics drop out.
// Stay OFF the K-line for `ms` (so a link can time out) while keeping the web server responsive.
static void busQuiet(uint32_t ms) {
  uint32_t t = millis();
  while (millis() - t < ms) { server.handleClient(); delay(5); }
}
static void slabsExcursion() {
  endSession();                                   // close the TD5 session cleanly (20 + 82)
  busQuiet(SLABS_SETTLE_MS);                       // ...then SILENCE so TD5's link releases before SLABS init
  bool ok = false;
  for (int i = 0; i < 3 && !ok; i++) {            // retry: a lingering link makes StartComm get 7F 81 10
    if (i) { stopComm(); busQuiet(SLABS_SETTLE_MS); }
    ok = slabsEstablish();
  }
  String line = String("slabs,vehicle=") + LOG_VEHICLE + " reachable=" + (ok ? "1i" : "0i");
  if (!isnan(lastSpeedKmh)) { line += ",speed="; line += String(lastSpeedKmh, 1); }
  if (!ok) { line += ",sb=\"" + klineLastBurst + "\""; }   // diagnostic: what did SLABS StartComm return?
  if (ok) {
    uint8_t b[80]; int n;
    n = td5ReadLid(0x54, b, sizeof b); if (n > 0) { line += ",h54=\"" + toHex(b, n) + "\""; }  // heights
    n = td5ReadLid(0x50, b, sizeof b); if (n > 0) { line += ",v50=\"" + toHex(b, n) + "\""; }  // ABS sensor V
    n = td5ReadLid(0x43, b, sizeof b); if (n > 0) { line += ",w43=\"" + toHex(b, n) + "\""; }  // wheel speeds
    // Fault blocks: 21 11 = LOGGED (historical — persists even though we can't catch current while
    // moving), 21 47 = current. Raw hex + a logged-fault bit count so Grafana shows when they appear.
    n = td5ReadLid(0x11, b, sizeof b);
    if (n > 0) {
      int c = 0; for (int i = 0; i < n; i++) for (int k = 0; k < 8; k++) if (b[i] & (1 << k)) c++;
      slabsFlog = toHex(b, n);                        // also expose to /live for browser decode
      line += ",flog=\"" + slabsFlog + "\",nflog=" + String(c) + "i";
      // Read-and-clear, once per ignition cycle (see slabsClear). Store first, then erase.
      if (n >= 16 && slabsClear && !slabsClearedBoot && slabsClearTries < 3) {
        long ts = epochNow();
        String pre = String("slabs_clear,vehicle=") + LOG_VEHICLE + " flog_before=\"" +
                     toHex(b, 16) + "\",nflog_before=" + String(c) + "i";
        if (ts) { pre += " "; pre += String(ts); }
        if (influxPost(pre) == 204) {                 // stored → safe to erase
          slabsClearTries++;
          bool ack = slabsClearFaults();
          uint8_t a[80];
          int m = td5ReadLid(0x11, a, sizeof a);       // verify: should now be empty
          int c2 = -1;
          if (m >= 16) {
            c2 = 0;
            for (int i = 0; i < 16; i++) for (int k = 0; k < 8; k++) if (a[i] & (1 << k)) c2++;
            slabsFlog = toHex(a, 16);
          }
          // Bits back right after the clear = a fault SLABS sets at power-up (static, not
          // intermittent): worth knowing on its own.
          String post = String("slabs_clear,vehicle=") + LOG_VEHICLE + " ack=" + String(ack ? 1 : 0) +
                        "i,nflog_after=" + String(c2) + "i";
          if (m >= 16) post += ",flog_after=\"" + slabsFlog + "\"";
          if (ts) { post += " "; post += String(ts); }   // same timestamp → merges with `pre`
          if (influxPost(post) != 204) spillLine(post);
          if (ack || c2 == 0) slabsClearedBoot = true;  // else retry at the next standstill sample
          Serial.printf("SLABS: logged faults cleared (ack %d, after %d bits)\n", ack ? 1 : 0, c2);
        }
      }
    }
    n = td5ReadLid(0x47, b, sizeof b);
    if (n > 0) { slabsFcur = toHex(b, n); line += ",fcur=\"" + slabsFcur + "\""; }  // current
  }
  stopComm();                                     // release SLABS
  long ts = epochNow(); if (ts) { line += " "; line += String(ts); }
  influxPost(line);
  sessionUp = false; recoveryCleared = true;      // bus is clean → fast TD5 re-establish (skip the long idle)
  quietUntil = millis() + 600; lastFuelMs = 0;
}

// ---------------- SLABS hold ----------------
// Post one hold-mode point; spill it if the uplink is down — the fault ORDER is the whole point of
// the test, so an onset during a hotspot dropout must not be lost.
static void holdPost(String line) {
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  if (influxPost(line) != 204) spillLine(line);
}
// Forget the hold session (the link was released elsewhere: mute / bridge / scan / mode switch).
// Deliberately posts nothing — only a session that dies on its own is a test result.
static void holdDrop() { holdUp = false; holdHaveCur = false; holdHaveLog = false; }
// Emit one `slabs_fault` point per bit that changed vs the previous block. The first block of a
// session is the baseline: bits already set are emitted with base=1 (present at connect, onset
// unknown) so they are not mistaken for onsets observed live.
static void holdEdges(const char *block, const uint8_t *now, uint8_t *prev, bool &have) {
  for (int i = 0; i < 16; i++) {
    uint8_t d = have ? (uint8_t)(now[i] ^ prev[i]) : now[i];
    for (int b = 0; b < 8; b++) {
      if (!(d & (1 << b))) continue;
      holdPost(String("slabs_fault,vehicle=") + LOG_VEHICLE + ",block=" + block +
               ",bit=" + String(i) + "." + String(b) +
               " state=" + String((now[i] >> b) & 1) + "i,seq=" + String(holdSeq) +
               "i,base=" + String(have ? 0 : 1) + "i");
    }
    prev[i] = now[i];
  }
  have = true;
}
// Session status: alive + how long it has survived + the latest raw wheel speeds / current block.
static void holdStatus(int alive) {
  String line = String("slabs_hold,vehicle=") + LOG_VEHICLE + " alive=" + String(alive) +
                "i,up_s=" + String((millis() - holdSince) / 1000) + "i,seq=" + String(holdSeq) + "i";
  if (holdW43.length())   line += ",w43=\"" + holdW43 + "\"";
  if (slabsFcur.length()) line += ",fcur=\"" + slabsFcur + "\"";
  holdPost(line);
}
static void holdEstablish() {
  endSession();                                   // TD5 session / any stale link off the bus (20 + 82)
  sessionUp = false; lastFuelMs = 0;
  busQuiet(SLABS_SETTLE_MS);
  bool ok = false;
  for (int i = 0; i < 3 && !ok; i++) {            // same retry as the excursion (7F 81 10 on a lingering link)
    if (i) { stopComm(); busQuiet(SLABS_SETTLE_MS); }
    ok = slabsEstablish();
  }
  if (!ok) {
    stopComm();
    holdNextTry = millis() + HOLD_RETRY_MS;
    // Expected once the car has moved (the 2026-08-29 finding) — logged so the timeline shows it.
    holdPost(String("slabs_hold,vehicle=") + LOG_VEHICLE + " alive=0i,estab=0i,sb=\"" + klineLastBurst + "\"");
    return;
  }
  holdUp = true; holdSince = millis(); holdLastTick = 0;
  holdMiss = 0; holdStep = 0; holdHaveCur = false; holdHaveLog = false;
  holdWheelN = 7;                                 // first wheel slot reads 21 11 → logged baseline early
  holdStatus(1);
}
static void holdTick() {
  uint32_t now = millis();
  if (!holdUp) {
    if (now < BOOT_QUIET_MS || (int32_t)(now - holdNextTry) < 0) return;
    holdEstablish();
    return;
  }
  if (now - holdLastTick < HOLD_TICK_MS) return;
  holdLastTick = now;
  uint8_t kind = HOLD_PATTERN[holdStep];
  holdStep = (holdStep + 1) % sizeof HOLD_PATTERN;
  uint8_t b[80];
  int n;
  bool ok;
  if (kind == 1) {
    ok = kwpRequest(0x3E, nullptr, 0, b, sizeof b) >= 0;     // BARE 3E — `3E 01` kills SLABS' session
  } else if (kind == 0) {
    holdSeq++;
    n = td5ReadLid(0x47, b, sizeof b);                       // current faults
    ok = n >= 0;
    if (n >= 16) { slabsFcur = toHex(b, 16); holdEdges("cur", b, holdCur, holdHaveCur); }
  } else if (++holdWheelN % 8 == 0) {
    n = td5ReadLid(0x11, b, sizeof b);                       // logged faults (~every 32 s)
    ok = n >= 0;
    if (n >= 16) { slabsFlog = toHex(b, 16); holdEdges("log", b, holdLog, holdHaveLog); }
  } else {
    n = td5ReadLid(0x43, b, sizeof b);                       // wheel speeds, raw
    ok = n >= 0;
    if (n > 0) holdW43 = toHex(b, n);
    if (holdWheelN % 3 == 1) holdStatus(1);                  // survival heartbeat ~every 12 s
  }
  if (ok) { holdMiss = 0; return; }
  if (++holdMiss < HOLD_MISS_MAX) return;
  holdLostAfterS = (now - holdSince) / 1000;
  holdStatus(0);                                             // the moment it died + how long it lived
  Serial.printf("HOLD: SLABS session lost after %lus\n", (unsigned long)holdLostAfterS);
  stopComm();
  holdDrop();
  holdNextTry = millis() + HOLD_RETRY_MS;
}

static const uint32_t RAW_FLUSH_MS = 3000;      // ship raw batches every ~3 s
static void logTick() {
  uint32_t now = millis();
  if (now - lastSpillFlush > SPILL_FLUSH_MS) { lastSpillFlush = now; flushSpill(); }  // drain offline backlog
  if (rawOn && now - lastRawFlush > RAW_FLUSH_MS) { lastRawFlush = now; rawFlush(); }
  if (slabsHold) { holdTick(); return; }        // hold mode owns the bus: no TD5, no excursions
  if (now - lastCycle < LOG_INTERVAL_MS) return;
  lastCycle = now;
  if (!sessionUp) {
    if (now < BOOT_QUIET_MS) return;              // skip the crank/immobiliser window at ignition-on
    if (!recoveryCleared) {                        // ONE clean teardown per recovery episode...
      endSession();                                // ...StopDiagnosticSession (20) + StopCommunication (82)
      recoveryCleared = true;
      quietUntil = now + RECOVERY_IDLE_MS;         // ...then SILENCE so the ECU actually drops it
      return;
    }
    if (now < quietUntil) return;                 // stay OFF the bus during the quiet window
    sessionUp = td5Establish();                    // PURE init (no 82 — keep the silence intact)
    if (sessionUp) { estabTries = 0; sessionMiss = 0; needIgnCycle = false; recoveryCleared = false; Serial.println("EST: SESSION UP"); }
    else {
      estabFails++;
      if (++estabTries >= IGN_HINT_AFTER) needIgnCycle = true;  // teardown+silence not clearing it → prompt key cycle
      uint32_t q = RECOVERY_IDLE_MS * (estabTries + 1);         // escalate the silence for a stubborn link
      quietUntil = millis() + (q > RECOVERY_IDLE_MAX ? RECOVERY_IDLE_MAX : q);
    }
    return;
  }
  // SLABS excursion (opt-in) — ONLY while stationary, where SLABS actually answers.
  if (slabsPoll && (isnan(lastSpeedKmh) || lastSpeedKmh < SLABS_STILL_KMH)
      && millis() - lastSlabs > SLABS_STILL_MS) {
    lastSlabs = millis();
    slabsExcursion();
    return;
  }
  // Ride through a transient bad read: a single unreadable cycle (weak K-line) should NOT nuke
  // the session — re-establishing is expensive. Only tear down after several misses in a row.
  if (!logCycle()) {
    if (++sessionMiss < SESSION_MISS_GRACE) return;   // tolerate a glitch; keep the session
    Serial.println("EST: SESSION LOST");
    sessionUp = false; sessionMiss = 0;
    recoveryCleared = false;                          // recovery block will endSession (20+82) then idle
    haveFaultBase = false;                            // re-baseline faults on the next session (don't re-emit)
    lastFuelMs = 0;                                    // pause fuel integration across the gap
  } else sessionMiss = 0;
}

// Bring up the WireGuard tunnel so the node has a fixed WG IP. The handshake needs
// valid wall-clock time → NTP first. Skipped if WG_PRIVATE_KEY is the placeholder.
static void wgStart() {
  if (strlen(WG_PRIVATE_KEY) < 40) { Serial.println("WG: no key set — skipping"); return; }
  Serial.println("WG: syncing time (NTP) ...");
  ntpStart();
  uint32_t t0 = millis();
  while (time(nullptr) < 1700000000 && millis() - t0 < 8000) delay(200);
  if (time(nullptr) < 1700000000) { Serial.println("WG: NTP failed — skipping"); return; }
  IPAddress ip; ip.fromString(WG_LOCAL_IP);
  Serial.printf("WG: connecting, local %s ...\n", WG_LOCAL_IP);
  wgUp = wg.begin(ip, WG_PRIVATE_KEY, WG_ENDPOINT, WG_PEER_PUBKEY, (uint16_t)WG_PORT);
  Serial.printf("WG: %s\n", wgUp ? "tunnel up" : "begin() failed");
}

// ---------------- WiFi ----------------
// Priority order, best first: home (direct uplink, OTA from the Mac), then the Pi's own
// access point (in the car: no phone needed, the Pi NATs it out — NetworkManager
// method=shared), then the phone hotspot. The node boots in seconds and the Pi in ~30 s,
// so the Pi's AP is usually NOT there at boot: the node must keep looking and move up to
// it later. Hence a non-blocking roaming loop (wifiTick) instead of a boot-time list walk:
//   - link down: async scan every WIFI_SCAN_DOWN_MS, join the best known SSID heard;
//   - link up on anything but the best: async scan every WIFI_SCAN_UP_MS, and move up if a
//     better known SSID is heard at >= WIFI_MIN_RSSI (leaving home → SurfsUp drops → the
//     scan finds discopi; on the phone → discopi comes up → the node moves to it).
// The old walk blocked loop() 8 s per network on every retry, which stalled the K-line.
#ifndef WIFI_SSID_CAR                   // the Pi's AP; older secrets.h files lack it
#define WIFI_SSID_CAR ""
#define WIFI_PW_CAR   ""
#endif
struct WifiNet { const char *ssid; const char *pw; };
static const WifiNet NETS[] = { {WIFI_SSID_1, WIFI_PW_1}, {WIFI_SSID_CAR, WIFI_PW_CAR},
                                {WIFI_SSID_2, WIFI_PW_2} };
static const int NNETS = sizeof NETS / sizeof NETS[0];
static const uint32_t WIFI_JOIN_MS      = 12000;   // give up on one association after this
static const uint32_t WIFI_SCAN_DOWN_MS = 15000;   // no link: look this often
static const uint32_t WIFI_SCAN_UP_MS   = 60000;   // on the phone: look for discopi this often
static const uint32_t WIFI_SCAN_CAR_MS  = 300000;  // on discopi: look for home only rarely
static const int      WIFI_MIN_RSSI     = -82;     // don't move up to a network barely heard
static int      wifiTry = -1;                      // NETS index being joined, -1 = none
static uint32_t wifiTryAt = 0, wifiNextScan = 0;
static bool     wifiScanning = false;
static bool     wifiTryUp = false;                 // the join in progress is a move-up
static uint32_t wifiBanUntil[NNETS] = {0};         // skip a network that just failed to join
static const uint32_t WIFI_BAN_UP_MS   = 600000;   // failed move-up (wrong PSK?): leave it 10 min,
static const uint32_t WIFI_BAN_DOWN_MS = 30000;    // or a move-up would drop the phone every minute
static uint32_t lastWgTry = 0;
static int      wifiForce = -1;                    // /wifi?use=…: stay on this one (not persisted)

static int wifiIndex(const String &ssid) {
  for (int i = 0; i < NNETS; i++)
    if (NETS[i].ssid && *NETS[i].ssid && ssid == NETS[i].ssid) return i;
  return -1;
}
// Last few roaming events, newest last, exposed on /wifi: the serial log can't be read in the
// field (opening the USB port resets the ESP on macOS).
static String wifiEv;
// Core 2.0.17 has no setScanTimeout(); the field is protected, so reach it through a subclass.
struct ScanTimeout : WiFiScanClass { static void set(uint32_t ms) { _scanTimeout = ms; } };
static uint32_t wifiScanAt = 0;
static void wifiNote(const String &m) {
  wifiEv += String((millis() - bootMs) / 1000) + "s " + m + "; ";
  if (wifiEv.length() > 600) wifiEv = wifiEv.substring(wifiEv.length() - 500);
  Serial.println("WiFi: " + m);
}
static void wifiBegin(int i) {
  Serial.printf("WiFi: joining %s ...\n", NETS[i].ssid);
  if (WiFi.status() == WL_CONNECTED) {
    // Moving up from a live link: let the disconnect finish first. On core 2.0.x a begin()
    // straight after disconnect() can be refused while the old link is still tearing down.
    WiFi.disconnect(false);
    for (uint32_t t0 = millis(); WiFi.status() == WL_CONNECTED && millis() - t0 < 1500; ) delay(20);
  }
  wl_status_t r = WiFi.begin(NETS[i].ssid, NETS[i].pw);
  wifiNote(String("join ") + NETS[i].ssid + " -> " + String((int)r));
  wifiTry = i; wifiTryAt = millis();
}
// A new network means a new local IP. The WG tunnel is deliberately LEFT UP: WireGuard
// roams by design (the next handshake/keepalive goes out from the new address and the
// server follows the endpoint). Tearing it down with wg.end() + begin() was tried
// 2026-11-12: once a panic at the switch, once a "tunnel up" that routed nothing
// (10.9.0.1 "Host is unreachable"). If WG was never up, loop() retries it at once.
// WireGuard-ESP32 makes its netif the default route at begin(). On every new DHCP lease
// esp_netif makes the STA netif default again, so after a roam 10.9.0.x traffic went out
// plain — on Discopi straight into the Pi's own wg0 — and the node's tunnel went silent:
// the server never learned its new endpoint and 10.9.0.9 stopped answering (2026-11-12).
static void wgReassertDefault() {
  if (!wgUp) return;
  struct netif *n;
  NETIF_FOREACH(n) {
    if (n->name[0] == 'w' && n->name[1] == 'g') { if (netif_default != n) netif_set_default(n); return; }
  }
}
static void wifiChanged() {
  lastWgTry = millis() - 30000;
  wgReassertDefault();
  if (WiFi.status() == WL_CONNECTED) ntpStart();   // on Discopi: the Pi's clock first
}
// Pick the best known SSID from a finished scan (or -1), then free the scan results.
// Best known network in the scan. With a pin (/wifi?use=…) the pinned one wins when it is
// usable, but if it is missing or banned the node falls back to the normal order rather than
// sitting with no network at all. Measured 2026-11-12: pinned to car, one failed Discopi join
// banned it for 10 min and the node went dark (no home either) until the ban ran out.
static int wifiBestFromScan(int n) {
  int best = -1;
  bool forcedOk = false;
  for (int k = 0; k < n; k++) {
    int i = wifiIndex(WiFi.SSID(k));
    if (i < 0 || WiFi.RSSI(k) < WIFI_MIN_RSSI) continue;
    if ((int32_t)(millis() - wifiBanUntil[i]) < 0) continue;
    if (i == wifiForce) forcedOk = true;
    if (best < 0 || i < best) best = i;
  }
  WiFi.scanDelete();
  return forcedOk ? wifiForce : best;
}
static void wifiTick() {
  uint32_t now = millis();
  bool up = WiFi.status() == WL_CONNECTED;
  if (wifiTry >= 0) {                                // an association is in progress
    if (up && WiFi.SSID() == NETS[wifiTry].ssid) {     // the NEW network, not a stale old link
      wifiCur = wifiTry; wifiTry = -1;
      wifiNote(String("up ") + NETS[wifiCur].ssid + " " + WiFi.localIP().toString() + " " + String(WiFi.RSSI()));
      wifiChanged();
      wifiNextScan = now + (wifiCur == WIFI_CAR ? WIFI_SCAN_CAR_MS : WIFI_SCAN_UP_MS);
    } else if (now - wifiTryAt > WIFI_JOIN_MS) {
      wifiNote(String(NETS[wifiTry].ssid) + " did not associate, banned");
      // A pinned network is retried sooner: the pin says the user wants exactly that one.
      wifiBanUntil[wifiTry] = now + (wifiTry == wifiForce ? WIFI_BAN_DOWN_MS
                                     : wifiTryUp ? WIFI_BAN_UP_MS : WIFI_BAN_DOWN_MS);
      wifiTry = -1; wifiCur = -1; wifiNextScan = now;
    }
    return;
  }
  if (!up && wifiCur >= 0) {                         // lost the link (e.g. drove away from home)
    wifiNote(String("lost ") + NETS[wifiCur].ssid);
    wifiCur = -1; wifiNextScan = now; wifiChanged();
  }
  if (up && wifiCur < 0) wifiCur = wifiIndex(WiFi.SSID());   // joined outside our bookkeeping
  if (up && wifiCur == (wifiForce >= 0 ? wifiForce : 0)) return;   // already on the best/forced one
  if (!wifiScanning) {
    if ((int32_t)(now - wifiNextScan) < 0) return;
    // Async: WiFi runs on core 0, so the K-line on core 1 keeps going.
    // Core 2.0.17 sets the async scan timeout to 20 x the per-channel time inside
    // scanNetworks() and checks it before the done bit. A scan made while CONNECTED is much
    // slower (the radio keeps going back to the home channel): measured 2026-11-12 still
    // running after 6.3 s at 300 ms/channel, so every scan from home read back as
    // WIFI_SCAN_FAILED and the node never moved up to Discopi. Widen the timeout AFTER the
    // start, since scanNetworks() overwrites it.
    int r = WiFi.scanNetworks(true, false, false, 120);
    ScanTimeout::set(30000);
    wifiScanAt = now;
    if (r == WIFI_SCAN_FAILED) {
      wifiNote("scan start failed");
      wifiNextScan = now + WIFI_SCAN_DOWN_MS; return;
    }
    wifiScanning = true; return;
  }
  int bits = WiFi.getStatusBits();
  int n = WiFi.scanComplete();
  if (n == WIFI_SCAN_RUNNING) return;
  wifiScanning = false;
  wifiNote(String("scan ") + (now - wifiScanAt) + "ms" + (n < 0 ? String(" bits=0x") + String(bits, HEX) : String("")));
  int best = n > 0 ? wifiBestFromScan(n) : -1;
  if (n < 0) WiFi.scanDelete();
  wifiNote(String("scan n=") + n + " best=" + best);
  if (up) wifiNextScan = now + (wifiCur == WIFI_CAR ? WIFI_SCAN_CAR_MS : WIFI_SCAN_UP_MS);
  else    wifiNextScan = now + WIFI_SCAN_DOWN_MS;
  bool better = wifiForce >= 0 ? best == wifiForce : best < wifiCur;
  if (best < 0 || (up && !better)) return;           // nothing (better) in range
  if (up) Serial.printf("WiFi: %s heard, moving up from %s\n", NETS[best].ssid, NETS[wifiCur].ssid);
  wifiBegin(best);
  wifiTryUp = up;
}
// Boot: one blocking scan + join so WG/OTA come up in setup() as before. If nothing is
// in range, wifiTick() takes over from loop() without blocking it.
static void wifiBoot() {
  int n = WiFi.scanNetworks(false, false, false, 120);
  int best = n > 0 ? wifiBestFromScan(n) : -1;
  if (best < 0) { Serial.println("WiFi: no known network in range (will keep looking)"); return; }
  wifiBegin(best); wifiTryUp = false;
  while (WiFi.status() != WL_CONNECTED && millis() - wifiTryAt < WIFI_JOIN_MS) delay(200);
  wifiTick();                                        // records success, or schedules a rescan
}

// "home" | "car" | "phone" | "none" — which uplink the node is on (for /data and the head unit).
static String wifiNetName() {
  if (WiFi.status() != WL_CONNECTED || wifiCur < 0) return "none";
  return wifiCur == 0 ? "home" : wifiCur == WIFI_CAR ? "car" : "phone";
}
// /wifi?use=car|home|phone|auto — pin the node to one network until reboot (not persisted),
// e.g. to test the Pi relay indoors where home WiFi would otherwise win. auto = priority.
static void handleWifi() {
  String u = server.arg("use");
  if (u.length()) {
    int f = u == "home" ? 0 : u == "car" ? WIFI_CAR : u == "phone" ? 2 : -1;
    if (f >= 0 && !(NETS[f].ssid && *NETS[f].ssid)) f = -1;   // not configured → stay auto
    wifiForce = f; wifiBanUntil[0] = wifiBanUntil[1] = wifiBanUntil[2] = 0;
    wifiNextScan = millis();
  }
  server.send(200, "application/json",
    String("{\"net\":\"") + wifiNetName() + "\",\"ssid\":\"" + WiFi.SSID() +
    "\",\"use\":\"" + (wifiForce < 0 ? "auto" : wifiForce == 0 ? "home" : wifiForce == WIFI_CAR ? "car" : "phone") +
    "\",\"ip\":\"" + WiFi.localIP().toString() + "\",\"ev\":\"" + wifiEv + "\"}");
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
      "</code> · last POST <code>" + String(lastPost) + "</code></li>"
    "<li>Bridge: <code>" + (bridgeMode ? String("ON — USB cable mode (host owns the bus)") : String("off")) +
      "</code></li></ul>"
    "<a class=btn href='/live'>Live data</a>"
    "<a class=btn href='/scan'>Test car (TD5 + SLABS)</a>"
    "<a class=btn href='/log?on=" + (logEnabled ? "0" : "1") + "'>" +
      (logEnabled ? "Stop logging" : "Start logging") + "</a>"
    "<a class=btn href='/bridge?on=" + (bridgeMode ? "0" : "1") + "'>" +
      (bridgeMode ? "Exit cable mode" : "Cable mode (USB)") + "</a>"
    "<p style='color:#888;font-size:13px'>Ignition on, node wired to OBD (K/12V/GND + 1k pull-up). "
    "Logs to InfluxDB <code>" + INFLUX_BUCKET + "</code> at <code>" + INFLUX_URL + "</code>.</p>";
  server.send(200, "text/html", html);
}
static void handleStatus() {
  uint32_t spillPending = 0;
  if (fsReady) {
    File sf = LittleFS.open(SPILL_PATH, FILE_READ);
    if (sf) { uint32_t s = sf.size(); spillPending = s > spillOffset ? s - spillOffset : 0; sf.close(); }
  }
  server.send(200, "application/json",
    "{\"ssid\":\"" + WiFi.SSID() + "\",\"ip\":\"" + WiFi.localIP().toString() +
    "\",\"rssi\":" + String(WiFi.RSSI()) +
    ",\"uptime_s\":" + String((millis()-bootMs)/1000) +
    ",\"wg\":" + String(wgUp ? 1 : 0) +
    ",\"logging\":" + String(logEnabled ? 1 : 0) +
    ",\"bridge\":" + String(bridgeMode ? 1 : 0) +
    ",\"session\":" + String(sessionUp ? 1 : 0) +
    ",\"demo\":" + String(demoMode ? 1 : 0) +
    ",\"ign_cycle\":" + String(needIgnCycle ? 1 : 0) +
    ",\"points\":" + String(pointsSent) +
    ",\"estab_fails\":" + String(estabFails) +
    ",\"last_post\":" + String(lastPost) +
    ",\"raw\":" + String(rawOn ? 1 : 0) +
    ",\"rawq\":" + String(rawBuf.length()) +
    ",\"raw_post\":" + String(lastRawCode) +
    ",\"spill\":" + String(spillPending) +
    ",\"spill_dropped\":" + String(spillDropped) + "}");
}
// Latest decoded snapshot as JSON — for /live and (later) an on-device screen.
static void handleData() {
  server.send(200, "application/json",
    "{\"age_ms\":" + String(latestMs ? (uint32_t)(millis() - latestMs) : 0) +
    ",\"session\":" + String(sessionUp || demoMode ? 1 : 0) +
    ",\"demo\":" + String(demoMode ? 1 : 0) +
    ",\"logging\":" + String(logEnabled ? 1 : 0) +
    ",\"bridge\":" + String(bridgeMode ? 1 : 0) +
    ",\"ign_cycle\":" + String(needIgnCycle ? 1 : 0) +
    ",\"slabs_poll\":" + String(slabsPoll ? 1 : 0) +
    ",\"slabs_clear\":" + String(slabsClear ? 1 : 0) +
    ",\"slabs_cleared\":" + String(slabsClearedBoot ? 1 : 0) +
    ",\"slabs_hold\":" + String(slabsHold ? 1 : 0) +
    ",\"hold_up\":" + String(holdUp ? 1 : 0) +
    ",\"hold_up_s\":" + String(holdUp ? (millis() - holdSince) / 1000 : 0) +
    ",\"hold_lost_s\":" + String(holdLostAfterS) +
    ",\"rssi\":" + String(WiFi.RSSI()) +
    ",\"net\":\"" + wifiNetName() + "\"" +
    ",\"faults\":\"" + faultsHex + "\"" +
    ",\"slabs_flog\":\"" + slabsFlog + "\"" +
    ",\"slabs_fcur\":\"" + slabsFcur + "\"" +
    ",\"signals\":" + (latestJson.length() ? latestJson : String("{}")) + "}");
}
// The live web UI (served at "/" and "/live") lives in its own header (live_html.h) so the
// Arduino auto-prototype generator doesn't parse its embedded JavaScript as C++.
static void handleLive() { server.send(200, "text/html", LIVE_HTML); }
static void handleScan() {
  // Pause logging around the manual scan so the two don't fight over the bus.
  bool was = logEnabled; logEnabled = false; sessionUp = false; holdDrop();
  String out = kwpStartComm(0x13, "TD5") + "\n" + kwpStartComm(0x29, "SLABS") + "\n";
  stopComm();                    // RELEASE the link /scan just opened (esp. SLABS' C1) — a link left
                                 // open here makes the logger's next TD5 StartComm get 7F 81 10.
  logEnabled = was;
  // /scan hit the bus (its own inits); force a fresh recovery (endSession → silence → init).
  recoveryCleared = false; estabTries = 0; needIgnCycle = false;
  server.send(200, "text/plain", out);
}
// ---------------- Demo mode ----------------
// A 120 s synthetic drive cycle: idle → pull away through the gears → 90 km/h cruise → brake →
// idle, with the coolant warming up over the first ~5 min and one TD5 fault bit raised for
// 20 s of each cycle (so a fault list/badge can be tested too). Values sit in each signal's
// realistic range and go through the same appendField/appendFuel path as real data, so the
// Influx line and /data JSON have exactly the real shape. Posted once a second; never spilled.
static uint32_t demoStart = 0, demoLast = 0;
static float demoNoise(float a) { return a * ((float)(esp_random() % 2001) / 1000.0f - 1.0f); }
static void demoTick() {
  uint32_t now = millis();
  if (now - demoLast < LOG_INTERVAL_MS) return;
  demoLast = now;
  float t = fmodf((now - demoStart) / 1000.0f, 120.0f);
  float warm = (now - demoStart) / 300000.0f; if (warm > 1) warm = 1;
  float speed, rpm, load;                          // load 0..1 drives throttle/boost/fuel
  if (t < 15)       { speed = 0; rpm = 760; load = 0.05f; }
  else if (t < 45)  { float u = (t - 15) / 30;     // 0→90 km/h through 4 gears
                      speed = 90 * u; float g = fmodf(u * 4, 1.0f);
                      rpm = 1100 + 1700 * g; load = 0.75f; }
  else if (t < 90)  { speed = 90 + 3 * sinf(t / 4); rpm = 2100 + 60 * sinf(t / 4); load = 0.35f; }
  else if (t < 110) { float u = (t - 90) / 20; speed = 90 * (1 - u); rpm = 2100 - 1340 * u; load = 0.02f; }
  else              { speed = 0; rpm = 760; load = 0.05f; }
  rpm += demoNoise(8); if (speed > 0) speed += demoNoise(0.5f); if (speed < 0) speed = 0;
  float inj = 6 + 50 * load + demoNoise(0.5f);
  float map = 1.01f + 1.1f * load + demoNoise(0.01f);

  String line = String("engine,vehicle=demo ");
  String js = "{"; bool first = true;
  appendField(line, js, first, "rpm", roundf(rpm));
  appendField(line, js, first, "speed", roundf(speed));
  appendField(line, js, first, "battery", 14.1f + demoNoise(0.05f));
  appendField(line, js, first, "coolant_c", 40 + 48 * warm + demoNoise(0.2f));
  appendField(line, js, first, "air_c", 18 + 10 * load + demoNoise(0.2f));
  appendField(line, js, first, "fuel_c", 25 + 15 * warm);
  appendField(line, js, first, "throttle_v", 0.5f + 3.5f * load);
  appendField(line, js, first, "map_bar", map);
  appendField(line, js, first, "maf", 300 + rpm * 0.25f * map + demoNoise(5));
  appendField(line, js, first, "maf_raw", 1800 + 900 * load);
  appendField(line, js, first, "inj_mg", inj);
  appendField(line, js, first, "egr_pct", load < 0.4f ? 40 : 0);
  appendField(line, js, first, "wastegate_pct", 20 + 60 * load);
  appendField(line, js, first, "rpm_error", roundf(demoNoise(15)));
  appendField(line, js, first, "ambient_bar", 1.013f);
  appendField(line, js, first, "balance_1", roundf(demoNoise(5)));
  appendField(line, js, first, "balance_2", roundf(demoNoise(5)));
  appendField(line, js, first, "balance_3", roundf(demoNoise(5)));
  appendField(line, js, first, "balance_4", roundf(demoNoise(5)));
  appendField(line, js, first, "balance_5", roundf(demoNoise(5)));
  bool fault = t >= 60 && t < 80;
  faultsHex = fault ? String("01") : String("00");
  for (int i = 1; i < 35; i++) faultsHex += "00";
  appendField(line, js, first, "nfaults", fault ? 1 : 0);
  appendFuel(line, js, first, (int)rpm, inj, speed);
  js += "}"; latestJson = js; latestMs = millis();
  long ts = epochNow();
  if (ts) { line += " "; line += String(ts); }
  lastPost = influxPost(line);                     // no spill: demo data isn't worth keeping
}
static void demoStop() {
  demoMode = false; latestJson = ""; latestMs = 0; faultsHex = "";
  tripFuel = tripDist = 0; lastFuelMs = 0; tripStartMs = 0;
  // Fresh recovery, as on unmute: endSession → silence → init.
  sessionUp = false; quietUntil = 0; recoveryCleared = false; estabTries = 0; needIgnCycle = false;
  holdNextTry = 0;
}
static void handleDemo() {
  if (server.hasArg("on")) {
    bool on = server.arg("on") != "0";
    if (on && !demoMode) {
      // Get off the bus the same way mute does (82 releases a TD5 or held SLABS link).
      sessionUp = false; holdDrop(); endSession(); recoveryCleared = true;
      demoMode = true; demoStart = millis(); demoLast = 0;
      tripFuel = tripDist = 0; lastFuelMs = 0; tripStartMs = 0; latestJson = ""; faultsHex = "";
    } else if (!on && demoMode) demoStop();
  }
  lastBeat = 0;                                    // tell the Pi at once
  server.send(200, "application/json", "{\"demo\":" + String(demoMode ? 1 : 0) + "}");
}

static void handleLog() {
  if (server.hasArg("on")) {
    logEnabled = server.arg("on") != "0";
    if (!logEnabled) {
      // MUTE: free the shared bus for another tool. Close cleanly (20+82) so the ECU doesn't
      // stay stuck, then stay off K-line (logTick won't run while logEnabled is false).
      sessionUp = false; lastFuelMs = 0; holdDrop();
      endSession(); recoveryCleared = true;     // 82 also releases a held SLABS link
    } else {
      // RESUME: fresh recovery (endSession → silence → init) — establishes as soon as it clears.
      quietUntil = 0; recoveryCleared = false; estabTries = 0; needIgnCycle = false;
      holdNextTry = 0;                          // hold mode: re-establish SLABS right away
    }
  }
  lastBeat = 0;                                // tell the Pi at once
  server.send(200, "application/json",
    "{\"logging\":" + String(logEnabled ? 1 : 0) + "}");
}

// ---------------- USB serial bridge (ESP as a K-line cable) ----------------
// Host line protocol (USB @ 115200, '\n'-terminated), same as the Python EspTransport speaks:
//   PING          -> "PONG"                 probe
//   INIT          -> "OK"                   fast-init pulse only
//   INIT AA BB .. -> "RX CC DD .."          pulse THEN write bytes + read burst (atomic: the
//                                           pulse->StartComm gap must not cross USB)
//   SLOWINIT AA   -> "RX 55 K1 K2 .."       5-baud slow init to address AA (BCU/airbag), done
//                                           locally (the W4 handshake can't cross the relay)
//   TX AA BB ..   -> "RX CC DD .."          write bytes, read the reply burst
//   STOP          -> "OK"                   StopCommunication (release the link)
// All framing / seed-key / decoding stays in the host; the ESP only owns the 25 ms pulse
// (which can't cross a link) and relays raw bytes — reusing kline_core's primitives.
static void bridgeEnter() {
  if (!bridgeMode) {
    bridgeMode = true;
    sessionUp = false; lastFuelMs = 0;     // drop our own logging session...
    holdDrop();                            // ...or the held SLABS one (endSession's 82 releases it)
    endSession(); recoveryCleared = true;  // ...close it cleanly (20+82) so the host inits clean
  }
  bridgeIdleUntil = millis() + BRIDGE_IDLE_MS;
}
static void bridgeExit() {
  bridgeMode = false; bridgeSticky = false;
  quietUntil = 0; recoveryCleared = false;     // fresh recovery (endSession → silence → init), then relog
  holdNextTry = 0;
  estabTries = 0; needIgnCycle = false;
}
static int bridgeNib(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  c |= 0x20;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}
static size_t bridgeParseHex(const String &s, uint8_t *out, size_t cap) {
  size_t n = 0; int i = 0, L = s.length();
  while (i < L && n < cap) {
    while (i < L && bridgeNib(s[i]) < 0) i++;             // skip spaces / non-hex
    if (i >= L) break;
    int hi = bridgeNib(s[i++]);
    int lo = (i < L && bridgeNib(s[i]) >= 0) ? bridgeNib(s[i++]) : -1;
    out[n++] = (lo < 0) ? (uint8_t)hi : (uint8_t)((hi << 4) | lo);
  }
  return n;
}
static void bridgePrintRx(const uint8_t *d, size_t n) {
  Serial.print("RX ");
  if (n) Serial.print(toHex(d, n));        // toHex: uppercase, space-separated (kline_core)
  Serial.println();
}
// Handle one USB command line. Returns true if it was a bridge command (→ take the bus).
static bool bridgeHandle(const String &line) {
  if (line.startsWith("PING")) { bridgeEnter(); Serial.println("PONG"); return true; }
  if (line.startsWith("INIT")) {
    bridgeEnter();
    klineFastInit();                        // the timing-critical pulse, done LOCALLY
    String rest = line.substring(4); rest.trim();
    if (rest.length() == 0) { Serial.println("OK"); return true; }
    uint8_t tx[80]; size_t n = bridgeParseHex(rest, tx, sizeof tx);
    while (Serial2.available()) Serial2.read();
    Serial2.write(tx, n); Serial2.flush();  // ...fused with the StartComm frame, atomically
    uint8_t rx[300]; size_t r = readBurst(rx, sizeof rx, 500, 40);
    bridgePrintRx(rx, r); return true;
  }
  if (line.startsWith("SLOWINIT")) {
    bridgeEnter();
    String rest = line.substring(8); rest.trim();     // the address byte in hex
    uint8_t addr[1]; size_t n = bridgeParseHex(rest, addr, 1);
    uint8_t rx[32];
    size_t r = (n >= 1) ? klineSlowInit(addr[0], rx, sizeof rx) : 0;  // the ~2 s handshake, LOCAL
    bridgePrintRx(rx, r); return true;
  }
  if (line.startsWith("TX")) {
    bridgeEnter();
    ensureSerial();
    uint8_t tx[80]; size_t n = bridgeParseHex(line.substring(2), tx, sizeof tx);
    while (Serial2.available()) Serial2.read();
    Serial2.write(tx, n); Serial2.flush();
    uint8_t rx[300]; size_t r = readBurst(rx, sizeof rx, 400, 40);
    bridgePrintRx(rx, r); return true;
  }
  if (line.startsWith("STOP")) { bridgeEnter(); stopComm(); Serial.println("OK"); return true; }
  return false;                             // not a bridge command (host banner / stray input)
}
static void serviceBridgeSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length()) bridgeHandle(line);
}
static void handleBridge() {
  if (server.hasArg("on")) {
    if (server.arg("on") != "0") { bridgeEnter(); bridgeSticky = true; }  // hold until Back to live
    else { bridgeExit(); lastBeat = 0; }                                  // back to autonomous logging
  }
  server.send(200, "application/json", "{\"bridge\":" + String(bridgeMode ? 1 : 0) + "}");
  if (bridgeMode && bridgeSticky) nodeHeartbeat();   // the only beat cable mode gets: bridge=1
}
static void handleSlabsPoll() {
  if (server.hasArg("on")) {
    slabsPoll = server.arg("on") != "0";
    if (slabsPoll) lastSlabs = 0;
    prefs.putBool("slabs", slabsPoll);       // persist so it survives a mid-drive reboot
  }
  server.send(200, "application/json", "{\"slabs_poll\":" + String(slabsPoll ? 1 : 0) + "}");
}
// Read-and-clear of SLABS' logged faults at start, on/off (persisted). Switch OFF before a
// workshop visit if they should see the history.
static void handleSlabsClear() {
  if (server.hasArg("on")) {
    slabsClear = server.arg("on") != "0";
    prefs.putBool("sclear", slabsClear);
  }
  server.send(200, "application/json", "{\"slabs_clear\":" + String(slabsClear ? 1 : 0) +
              ",\"cleared\":" + String(slabsClearedBoot ? 1 : 0) + "}");
}
// SLABS hold on/off. ON: the next logTick tears TD5 down and holds SLABS (establish only succeeds
// at a standstill after an ignition cycle). OFF: release SLABS and run the normal TD5 recovery.
static void handleSlabsHold() {
  if (server.hasArg("on")) {
    bool on = server.arg("on") != "0";
    if (on != slabsHold) {
      slabsHold = on;
      if (on) { sessionUp = false; lastFuelMs = 0; holdDrop(); holdNextTry = 0; }
      else {
        if (holdUp) stopComm();
        holdDrop();
        sessionUp = false; quietUntil = 0; recoveryCleared = false; estabTries = 0; needIgnCycle = false;
      }
      prefs.putBool("hold", slabsHold);      // persist: survives a reboot, so every drive is a run
    }
  }
  server.send(200, "application/json",
    "{\"slabs_hold\":" + String(slabsHold ? 1 : 0) + ",\"hold_up\":" + String(holdUp ? 1 : 0) + "}");
}

void setup() {
  Serial.begin(115200); Serial.setTimeout(80); delay(300); bootMs = millis();
  Serial.println("\n== K-line node: WiFi + OTA + web + K-line + Influx ==");
  fsReady = LittleFS.begin(true);            // mount (format on first boot) for the offline spill
  Serial.printf("LittleFS: %s\n", fsReady ? "mounted" : "FAILED");
  prefs.begin("node", false);                // NVS: restore persisted settings…
  slabsPoll = prefs.getBool("slabs", true);  // …default ON (excursion is standstill-only + read-only,
                                             // safe; captures SLABS heights/ABS-V/faults at every stop)
  slabsHold = prefs.getBool("hold", false);  // SLABS hold (fault-order test) — off unless chosen
  slabsClear = prefs.getBool("sclear", true); // read-and-clear SLABS logged faults once per start
  Serial.printf("Boot reason: %s · slabs_poll %s · slabs_hold %s\n", resetReasonStr(),
                slabsPoll ? "ON" : "off", slabsHold ? "ON" : "off");
  // Auto-reconnect off: it would keep retrying the lost network and fight the roaming
  // scan. wifiTick() rejoins the same network itself when that is still the best one.
  WiFi.mode(WIFI_STA); WiFi.setHostname(OTA_HOSTNAME); WiFi.setAutoReconnect(false);
  wifiBoot();
  wgStart();                                 // fixed WG IP, reachable via the tunnel

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  // Suspend K-line/logging while an OTA image is uploading — a mid-flash bus read
  // would only steal cycles from the write.
  ArduinoOTA.onStart([]() { logEnabled = false; sessionUp = false; holdDrop(); });
  ArduinoOTA.begin();                       // also starts mDNS as OTA_HOSTNAME
  MDNS.addService("http", "tcp", 80);       // advertise the web server (shows up in Fing/Bonjour)

  server.on("/", handleLive);               // startup = the polished live view
  server.on("/info", handleRoot);           // WiFi/IP/OTA status page (debug)
  server.on("/status", handleStatus);
  server.on("/live", handleLive);
  server.on("/data", handleData);
  server.on("/scan", handleScan);
  server.on("/log", handleLog);
  server.on("/bridge", handleBridge);       // put the node in USB cable mode (or auto on a USB cmd)
  server.on("/slabs", handleSlabsPoll);     // toggle the sparse SLABS excursion
  server.on("/slabshold", handleSlabsHold); // SLABS hold mode (fault-order test, T-23)
  server.on("/slabsclear", handleSlabsClear);
  server.on("/demo", handleDemo);           // ?on=1|0 — synthetic drive data, RAM only
  server.on("/wifi", handleWifi);           // ?use=car|home|phone|auto — pin a network (testing) // read-and-clear SLABS logged faults at start
  server.begin();

  logEnabled = influxConfigured();          // auto-start logging if a token is set
  rawOn = rawConfigured();                   // raw TX/RX streaming if a collector token is set
  rawBuf.reserve(30000);                     // avoid heap fragmentation from repeated growth
  klineRawTap = rawCapture;                  // let the comms core feed raw TX/RX to the logger
  Serial.printf("Web http://%s/  · /scan tests the car · logging %s · raw %s · OTA '%s'.\n",
                WiFi.localIP().toString().c_str(), logEnabled ? "ON" : "off",
                rawOn ? "ON" : "off", OTA_HOSTNAME);
}

static uint32_t lastKeepalive = 0;
void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  serviceBridgeSerial();                     // a host tool may take over the bus over USB
  if (bridgeMode) {
    // AUTO (USB) mode resumes logging after idle; web-selected (sticky) mode holds until Back to live.
    if (!bridgeSticky && (int32_t)(millis() - bridgeIdleUntil) > 0) bridgeExit();
    return;                                  // bus belongs to the host; skip WiFi churn + logging
  }
  // Heartbeat on the loop, not in logTick, so it also runs while muted and in demo mode.
  if (millis() - lastBeat > BEAT_INTERVAL_MS) { lastBeat = millis(); nodeHeartbeat(); }
  wifiTick();                                // non-blocking roaming: rejoin / move up to discopi
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
    wgReassertDefault();                     // a DHCP renew can hand the default back to STA
    kaUdp.beginPacket(IPAddress(10, 9, 0, 1), 51820);  // any WG-net IP → routes via wg → NAT refresh
    kaUdp.write((uint8_t)0);
    kaUdp.endPacket();
  }
  if (demoMode) demoTick();
  else if (logEnabled) logTick();
}
