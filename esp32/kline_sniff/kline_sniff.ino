// kline_sniff.ino — PASSIVE K-line sniffer (RX-only) via a high-impedance tap on GPIO16.
//
// Hardware (your tap): OBD pin7 (K-line) -> 220k -> BC337 base; collector -> GPIO16
//   + 10k pullup to 3V3; emitter -> GND; OBD pin4/5 -> ESP32 GND. Inverting
//   => KLINE_INVERT=true. NO TX on the K-line => can NEVER drive the bus (read-only).
//
// Reads the K-line @10400 8N1, splits it into frames on silence gaps, sends hex +
// timestamp (ms) over USB serial @115200. *** NEVER TRANSMITS. ***
// Run stationary, ignition on. Test first: does the reference tool reach the car with the tap in place?

#include <Arduino.h>

static const int      PIN_KRX      = 16;      // Q collector -> GPIO16
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = true;    // the transistor tap inverts
static const uint32_t GAP_MS       = 7;       // silence that ends a frame

static uint8_t  buf[512];
static size_t   n = 0;
static uint32_t lastByteMs = 0;

static void flushFrame() {
  if (n == 0) return;
  Serial.printf("[%9lu] ", (unsigned long)millis());
  for (size_t i = 0; i < n; i++) Serial.printf("%02x ", buf[i]);
  Serial.println();
  n = 0;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("# kline_sniff RX-only @10400 invert, GPIO16 — NEVER transmits");
  // txPin = -1 => no TX pin routed => impossible to drive the K-line.
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, -1, KLINE_INVERT);
}

void loop() {
  while (Serial2.available()) {
    uint8_t b = (uint8_t)Serial2.read();
    if (n < sizeof(buf)) buf[n++] = b;
    lastByteMs = millis();
  }
  if (n > 0 && (millis() - lastByteMs) > GAP_MS) flushFrame();
}
