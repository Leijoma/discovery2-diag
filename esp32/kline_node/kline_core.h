// kline_core.h — K-line / KWP2000 / Td5 communication core (reusable, standalone).
//
// This is the COMMS half of the node: fast init, KWP2000 framing, the Td5 seed→key,
// LID reads, and the decode table generated from signals/td5.json. It has NO dependency
// on WiFi / InfluxDB / the web server / logging — so it compiles and runs on its own and
// can be reused by other sketches. Raw TX/RX capture is exposed as an OPTIONAL hook
// (klineRawTap): the logging layer points it at its own capture function; left null, the
// comms core stays completely silent about storage.
//
// Requires only the Arduino core + the generated signal table. Uses Serial2 for K-line.
#pragma once
#include <Arduino.h>

// Optional raw TX/RX tap. The logging layer sets this; null = no capture (pure comms).
static void (*klineRawTap)(const char *dir, const uint8_t *d, size_t n) = nullptr;

// ---------------- LID decode table (generated) ----------------
// enum Kind / struct Field must precede the generated header (it uses U8/U16/S16 + Field).
enum Kind { U8, U16, S16 };
struct Field { const char *key; uint8_t lid; uint8_t off; uint8_t kind; float scale; float bias; };
// FIELDS[]/LIDS[]/NLIDS are GENERATED from src/d2diag/signals/td5.json — one source of
// truth for both platforms. Regenerate with: python3 tools/gen_signal_header.py
#include "signals_td5.h"

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
// Close OUR Td5 session cleanly: StopDiagnosticSession (20) THEN StopCommunication (82) —
// exactly like the KKL/Python end_session. The node OPENS a diagnostic session (10 A0) but
// only ever sent 82, leaving that diag session open; on RDL016 (2026-08-27) that left the ECU
// stuck (7F 81 10 to every re-init) until an ignition cycle. Send 20 first so the session is
// actually torn down, then 82 to drop the link. Call whenever WE had a session (mute / cable /
// lost read). Establish/leftover-clearing is different — that's 82-once-then-silence (below).
static void endSession() {
  ensureSerial();
  uint8_t stopSess[3] = { 0x01, 0x20, 0x21 };    // StopDiagnosticSession (20)
  while (Serial2.available()) Serial2.read();
  Serial2.write(stopSess, 3); Serial2.flush();
  uint8_t tmp[16];
  readBurst(tmp, sizeof tmp, 200, 30);           // absorb 60 (positive) / 7F, let the ECU process it
  stopComm();                                    // then StopCommunication (82)
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

// 5-baud slow init (ISO 9141 / ISO 14230-1) to `address` — for modules that don't do fast init
// (BCU 0x40, airbag 0x5B). Bit-bang the address at 5 baud (start bit + 8 data LSB-first + stop,
// 200 ms/bit), then read the ECU's sync 0x55 + key bytes KW1/KW2, wait W4, send ~KW2, and read the
// ~address confirmation. Fills `out` with ALL bytes received (55 KW1 KW2 [echo ~addr]) and returns
// the count; empty / no leading 0x55 = no module answered. Mirrors SerialTransport.slow_init. Done
// LOCALLY (like klineFastInit) because the ~25-50 ms W4 window can't survive a USB/BT relay round-trip.
static size_t klineSlowInit(uint8_t address, uint8_t *out, size_t cap) {
  const uint32_t BIT_MS = 200, W4_MS = 30;
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(BIT_MS);   // idle (high) before start
  uint8_t bits[10]; size_t nb = 0;
  bits[nb++] = 0;                                     // start bit
  for (int i = 0; i < 8; i++) bits[nb++] = (address >> i) & 1;       // 8 data bits, LSB first
  bits[nb++] = 1;                                     // stop bit
  for (size_t i = 0; i < nb; i++) {
    if (bits[i]) digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // 1 = idle/high
    else         digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW);   // 0 = break/low
    delay(BIT_MS);
  }
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // back to idle
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
  serial2Up = true;
  while (Serial2.available()) Serial2.read();          // discard RX garbage from our own bit-bang
  if (cap < 6) return 0;
  size_t got = readBytes(out, 3, 500);                 // 0x55, KW1, KW2
  if (got >= 3 && out[0] == 0x55) {
    uint8_t inv = (uint8_t)(~out[2]);                  // ~KW2 back to the ECU after W4
    delay(W4_MS);
    while (Serial2.available()) Serial2.read();
    Serial2.write(&inv, 1); Serial2.flush();
    got += readBytes(out + got, 3, 300);               // half-duplex echo + ~address confirmation
  }
  return got;
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
  if (klineRawTap) klineRawTap("TX", req, n);
  Serial2.write(req, n); Serial2.flush();

  uint8_t burst[96];
  size_t got = readBurst(burst, sizeof burst, 250, 30);
  if (klineRawTap) klineRawTap("RX", burst, got);
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
// PURE init: no 82 here. Clearing a leftover link is the CALLER's job — send the teardown
// (endSession = 20+82) ONCE, then keep the bus SILENT (sending anything, even 82, each attempt
// resets the ECU's wait — the lesson from the KKL _establish, whose idle is a QUIET period).
// The caller does teardown → silence → td5Establish(), and escalates the silence / prompts an
// ignition cycle if it stays stuck.
static bool td5Establish() {
  klineFastInit();
  // StartCommunication (addressed 81 13 F7 81) → expect C1 in the burst.
  uint8_t req[5] = { 0x81, TD5_ADDR, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);
  while (Serial2.available()) Serial2.read();
  if (klineRawTap) klineRawTap("TX", req, 5);
  Serial2.write(req, 5); Serial2.flush();
  uint8_t burst[32];
  size_t got = readBurst(burst, sizeof burst, 500, 40);
  if (klineRawTap) klineRawTap("RX", burst, got);
  // Require the real StartCommunication key bytes (C1 57 8F), not just any 0xC1. A
  // floating K-line on the bench otherwise false-positives on noise and logs garbage;
  // both Td5 and SLABS answer 57 8F, so this is exact for the car.
  // On every failure after fast init, tear the link down (stopComm) before returning —
  // a half-opened link left behind is exactly what makes the NEXT StartCommunication get
  // 7F 81 10 (generalReject), which then never self-clears.
  int ci = findSeq(burst, got, 0xC1, 0x57);
  // No C1 — either a silent bus or 7F 81 10 (generalReject = a link is still open and the 82
  // above did not clear it). We already sent our teardown; just fail and let the caller retry
  // (and, after enough rejects, prompt an ignition cycle). Print the burst so a stuck link
  // (7F 81 10) is distinguishable from a silent bus (empty) over serial.
  if (ci < 0 || ci + 2 >= (int)got || burst[ci + 2] != 0x8F) {
    Serial.print("EST: no C1, burst=["); Serial.print(got ? toHex(burst, got) : String("silent")); Serial.println("]");
    return false;
  }

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

// Minimal SLABS bring-up: fast init + StartCommunication (81 29 F7 81) → expect C1 57 8F.
// SLABS needs no diagnostic session/security (services work right after C1), so this is all it
// takes before reading 21 xx (unaddressed, via td5ReadLid). Returns true if it answered C1.
static const uint8_t SLABS_ADDR = 0x29;
static String klineLastBurst;                  // last StartComm reply burst (diagnostic: silent vs 7F 81 10)
static bool slabsEstablish() {
  klineFastInit();
  uint8_t req[5] = { 0x81, SLABS_ADDR, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);
  while (Serial2.available()) Serial2.read();
  Serial2.write(req, 5); Serial2.flush();
  uint8_t burst[32];
  size_t got = readBurst(burst, sizeof burst, 500, 40);
  klineLastBurst = got ? toHex(burst, got) : String("silent");   // strip our own echo? keep raw for RE
  return findSeq(burst, got, 0xC1, 0x57) >= 0;
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
