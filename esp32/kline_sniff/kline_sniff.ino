// kline_sniff.ino — PASSIV K-line-sniffer (RX-only) via högimpedanstapp på GPIO16.
//
// Hårdvara (din tapp): OBD pin7 (K-line) -> 220k -> BC337 bas; kollektor -> GPIO16
//   + 10k pullup till 3V3; emitter -> GND; OBD pin4/5 -> ESP32 GND. Inverterande
//   => KLINE_INVERT=true. INGEN TX på K-linen => kan ALDRIG driva bussen (read-only).
//
// Läser K-line @10400 8N1, delar upp i ramar på tystnadsgap, skickar hex +
// tidsstämpel (ms) över USB-serial @115200. *** SÄNDER ALDRIG. ***
// Kör stillastående, tändning på. Testa först: når reference toolen bilen med tappen i?

#include <Arduino.h>

static const int      PIN_KRX      = 16;      // Q-kollektor -> GPIO16
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = true;    // transistortappen inverterar
static const uint32_t GAP_MS       = 7;       // tystnad som avslutar en ram

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
  Serial.println("# kline_sniff RX-only @10400 invert, GPIO16 — sander ALDRIG");
  // txPin = -1 => ingen TX-pinne routad => omojligt att driva K-linen.
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
