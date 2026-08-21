// kline_test.ino — Td5 K-Line bring-up for the ESP32
//
// UART2: RX = GPIO16, TX = GPIO17, 10400 baud 8N1.
// Assumes a K-Line transceiver (e.g. L9637D) between the ESP32 and the K-line (12 V).
// K-line idles HIGH. The transceiver is assumed NON-inverting — set KLINE_INVERT
// true if your interface inverts the signal.
//
// Mirrors the Python library's logic: addressed StartCommunication frame
// 81 13 F7 81 0C, 8-bit checksum, half-duplex echo.

#include <Arduino.h>

static const int      PIN_KRX      = 16;   // Q2 collector -> GPIO16
static const int      PIN_KTX      = 17;   // GPIO17 -> 4.7k -> Q1 base
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = true;    // the 2-transistor circuit inverts both legs

// Td5 addresses
static const uint8_t ECU_ADDR    = 0x13;
static const uint8_t TESTER_ADDR = 0xF7;

static uint8_t checksum(const uint8_t *d, size_t n) {
  uint16_t s = 0;
  for (size_t i = 0; i < n; i++) s += d[i];
  return (uint8_t)(s & 0xFF);
}

static void printHex(const char *tag, const uint8_t *d, size_t n) {
  Serial.print(tag);
  for (size_t i = 0; i < n; i++) {
    if (d[i] < 0x10) Serial.print('0');
    Serial.print(d[i], HEX);
    Serial.print(' ');
  }
  Serial.println();
}

// Read up to n bytes, block at most timeout_ms. Returns the number read.
static size_t readBytes(uint8_t *buf, size_t n, uint32_t timeout_ms) {
  size_t got = 0;
  uint32_t start = millis();
  while (got < n && (millis() - start) < timeout_ms) {
    while (Serial2.available() && got < n) buf[got++] = (uint8_t)Serial2.read();
  }
  return got;
}

// ISO 14230-2 fast init: bit-bang the wakeup pattern on the TX pin, then start the UART.
static void klineFastInit() {
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // K-line idle (high)
  delay(300);                                         // W5: bus idle before init
  digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW);   // TiniL: 25 ms low
  delay(25);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // 25 ms high
  delay(25);
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
}

// Send StartCommunication, read echo + response.
static bool startCommunication() {
  uint8_t req[5] = { (uint8_t)(0x80 | 1), ECU_ADDR, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);

  while (Serial2.available()) Serial2.read();  // drain junk
  printHex("TX   ", req, 5);
  Serial2.write(req, 5);
  Serial2.flush();

  uint8_t echo[5];
  size_t e = readBytes(echo, 5, 300);          // half-duplex echo
  printHex("ECHO ", echo, e);

  uint8_t resp[16];
  size_t r = readBytes(resp, sizeof(resp), 500);
  if (r) { printHex("RX   ", resp, r); return true; }
  Serial.println("RX   (no response)");
  return false;
}

// Bench test without the car: send a byte, check the transceiver echoes it back.
// NOTE: needs the K-line side powered (12 V + pull-up), otherwise no echo.
static void klineSelfTest() {
  while (Serial2.available()) Serial2.read();
  uint8_t t = 0xA5;
  Serial2.write(&t, 1);
  Serial2.flush();
  uint8_t got;
  size_t n = readBytes(&got, 1, 100);
  if (n == 1 && got == t)      Serial.println("Self-test: OK (echo received)");
  else if (n == 1)             { Serial.print("Self-test: echo differed 0x"); Serial.println(got, HEX); }
  else                         Serial.println("Self-test: NO echo — check TX/RX/transceiver/pull-up/12V");
}

// DC-level diagnostics: drive TX, read RX directly. Shows whether the loop closes at all,
// whether it inverts, or whether TX/RX are swapped — independent of UART timing.
static void klineLineDiag() {
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  pinMode(PIN_KRX, INPUT);
  digitalWrite(PIN_KTX, HIGH); delay(5);
  int rxIdle = digitalRead(PIN_KRX);
  digitalWrite(PIN_KTX, LOW);  delay(5);
  int rxLow = digitalRead(PIN_KRX);
  digitalWrite(PIN_KTX, HIGH); delay(5);
  Serial.print("Line diag: TX=HIGH -> RX="); Serial.print(rxIdle);
  Serial.print("   TX=LOW -> RX="); Serial.println(rxLow);
  if (rxIdle == 1 && rxLow == 0)
    Serial.println("  => loop closes, non-inverted (good); KLINE_INVERT=false is correct");
  else if (rxIdle == 0 && rxLow == 1)
    Serial.println("  => INVERTED => set KLINE_INVERT=true");
  else
    Serial.println("  => RX does NOT follow TX: broken loop / no 12V / TX-RX swapped");
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n== Td5 K-Line bring-up (ESP32 UART2 16/17, 10400 8N1) ==");
  klineLineDiag();
  delay(50);
  klineSelfTest();
  Serial.println("Send any character in the serial monitor for fast init + StartCommunication.");
}

void loop() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    Serial.println("\n-- fast init + StartCommunication --");
    klineFastInit();
    startCommunication();
  }
}
