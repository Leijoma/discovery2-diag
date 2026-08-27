// kline_bridge.ino — turn the ESP32 + L9637D into a K-line front-end for a host tool,
// over USB serial. Makes the ESP "just another cable": the host (Python EspTransport)
// drives the whole KWP2000/Td5 protocol; the ESP only does the timing-critical fast-init
// pulse LOCALLY and relays raw bytes to/from K-line. No WiFi, no logging, no decoding —
// so plugging the ESP into the Mac does the same job as the KKL cable, freeing the cable.
//
// Protocol (line-based, USB @ 115200; host sends '\n'-terminated commands):
//   PING            -> "PONG"                 (probe the port)
//   INIT            -> "OK"                   fast-init pulse only
//   INIT AA BB ..   -> "RX CC DD .."          pulse THEN write those bytes + read burst (atomic:
//                                             the pulse->StartCommunication gap can't cross USB)
//   TX AA BB ..     -> "RX CC DD .."          write those bytes, read the reply burst (~400 ms)
//   STOP            -> "OK"                   StopCommunication (01 82 83)
//
// This is deliberately dumb: all framing / init sequencing / seed-key / decoding stays in
// the host. The one thing that can't cross a link (the 25 ms pulse) is done here.
//
// Wiring = the proven L9637D setup (hardware/README.md): RX pin1->GPIO16, TX pin4->GPIO17,
// VS->12V, K->OBD7 + 1k pull-up to 12V, common ground. KLINE_INVERT=false (non-inverting).

static const int      PIN_KRX      = 16;
static const int      PIN_KTX      = 17;
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = false;
static bool           serial2Up    = false;

static void ensureSerial2() {
  if (!serial2Up) {
    Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
    serial2Up = true;
  }
}
static void klineFastInit() {                    // ISO 14230-2 fast init (25 ms low, 25 ms high)
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(300);   // W5 idle high
  digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW); delay(25);    // 25 ms low
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH); delay(25);    // 25 ms high
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
  serial2Up = true;
}
// Read the reply burst (echo + response): bytes until `gap` ms of silence, or `overall` ms.
static size_t readBurst(uint8_t *buf, size_t cap, uint32_t overall, uint32_t gap) {
  size_t got = 0; uint32_t t0 = millis(), last = t0;
  while (millis() - t0 < overall) {
    if (Serial2.available()) { uint8_t b = Serial2.read(); if (got < cap) buf[got++] = b; last = millis(); }
    else if (got > 0 && millis() - last > gap) break;
  }
  return got;
}
static int hexNib(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  c |= 0x20;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}
static size_t parseHex(const String &s, uint8_t *out, size_t cap) {
  size_t n = 0; int i = 0, L = s.length();
  while (i < L && n < cap) {
    while (i < L && hexNib(s[i]) < 0) i++;               // skip spaces / non-hex
    if (i >= L) break;
    int hi = hexNib(s[i++]);
    int lo = (i < L && hexNib(s[i]) >= 0) ? hexNib(s[i++]) : -1;
    out[n++] = (lo < 0) ? (uint8_t)hi : (uint8_t)((hi << 4) | lo);
  }
  return n;
}
static void printHex(const uint8_t *d, size_t n) {
  char b[4];
  for (size_t i = 0; i < n; i++) { snprintf(b, sizeof b, "%02X ", d[i]); Serial.print(b); }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(60);                          // don't block long on a partial line
  ensureSerial2();
  Serial.println("BRIDGE ready");                 // banner; host flushes past it
}
void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("PING")) {
    Serial.println("PONG");
  } else if (line.startsWith("INIT")) {
    // Fast-init pulse, then (atomically, so the pulse->StartComm gap stays tight — a USB
    // round-trip here would miss the fast-init window) optionally write the StartComm frame
    // and read its burst. "INIT" alone = pulse + "OK"; "INIT 81 13 .." = pulse + TX + "RX ..".
    klineFastInit();
    String rest = line.substring(4); rest.trim();
    if (rest.length() == 0) {
      Serial.println("OK");
    } else {
      uint8_t tx[80]; size_t n = parseHex(rest, tx, sizeof tx);
      while (Serial2.available()) Serial2.read();
      Serial2.write(tx, n); Serial2.flush();
      uint8_t rx[300]; size_t r = readBurst(rx, sizeof rx, 500, 40);
      Serial.print("RX "); printHex(rx, r); Serial.println();
    }
  } else if (line.startsWith("TX")) {
    uint8_t tx[80];
    size_t n = parseHex(line.substring(2), tx, sizeof tx);
    ensureSerial2();
    while (Serial2.available()) Serial2.read();    // drop stale bytes
    Serial2.write(tx, n); Serial2.flush();
    uint8_t rx[300];
    size_t r = readBurst(rx, sizeof rx, 400, 40);
    Serial.print("RX "); printHex(rx, r); Serial.println();
  } else if (line.startsWith("STOP")) {
    ensureSerial2();
    uint8_t s[3] = { 0x01, 0x82, 0x83 };
    while (Serial2.available()) Serial2.read();
    Serial2.write(s, 3); Serial2.flush();
    uint8_t rx[16]; readBurst(rx, sizeof rx, 120, 30);
    Serial.println("OK");
  } else {
    Serial.println("ERR unknown");
  }
}
