// kline_test.ino — Td5 K-Line bring-up för ESP32
//
// UART2: RX = GPIO16, TX = GPIO17, 10400 baud 8N1.
// Förutsätter en K-Line-transceiver (t.ex. L9637D) mellan ESP32 och K-line (12 V).
// K-line vilar HÖG. Transceivern antas ICKE-inverterande — sätt KLINE_INVERT
// true om din interface inverterar signalen.
//
// Speglar Python-bibliotekets logik: adresserad StartCommunication-ram
// 81 13 F7 81 0C, 8-bitars checksumma, halv-duplex-eko.

#include <Arduino.h>

static const int      PIN_KRX      = 16;
static const int      PIN_KTX      = 17;
static const uint32_t KLINE_BAUD   = 10400;
static const bool     KLINE_INVERT = false;   // true om din interface inverterar

// Td5-adresser
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

// Läs upp till n bytes, blockera högst timeout_ms. Returnerar antal lästa.
static size_t readBytes(uint8_t *buf, size_t n, uint32_t timeout_ms) {
  size_t got = 0;
  uint32_t start = millis();
  while (got < n && (millis() - start) < timeout_ms) {
    while (Serial2.available() && got < n) buf[got++] = (uint8_t)Serial2.read();
  }
  return got;
}

// ISO 14230-2 fast init: bit-banga wakeup-mönstret på TX-pinnen, starta sedan UART.
static void klineFastInit() {
  Serial2.end();
  pinMode(PIN_KTX, OUTPUT);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // K-line idle (hög)
  delay(300);                                         // W5: buss-idle före init
  digitalWrite(PIN_KTX, KLINE_INVERT ? HIGH : LOW);   // TiniL: 25 ms låg
  delay(25);
  digitalWrite(PIN_KTX, KLINE_INVERT ? LOW : HIGH);   // 25 ms hög
  delay(25);
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
}

// Skicka StartCommunication, läs eko + svar.
static bool startCommunication() {
  uint8_t req[5] = { (uint8_t)(0x80 | 1), ECU_ADDR, TESTER_ADDR, 0x81, 0 };
  req[4] = checksum(req, 4);

  while (Serial2.available()) Serial2.read();  // töm skräp
  printHex("TX   ", req, 5);
  Serial2.write(req, 5);
  Serial2.flush();

  uint8_t echo[5];
  size_t e = readBytes(echo, 5, 300);          // halv-duplex-eko
  printHex("ECHO ", echo, e);

  uint8_t resp[16];
  size_t r = readBytes(resp, sizeof(resp), 500);
  if (r) { printHex("RX   ", resp, r); return true; }
  Serial.println("RX   (inget svar)");
  return false;
}

// Bänktest utan bilen: skicka en byte, se att transceivern ekar tillbaka den.
// OBS: kräver att K-line-sidan är matad (12 V + pull-up), annars inget eko.
static void klineSelfTest() {
  while (Serial2.available()) Serial2.read();
  uint8_t t = 0xA5;
  Serial2.write(&t, 1);
  Serial2.flush();
  uint8_t got;
  size_t n = readBytes(&got, 1, 100);
  if (n == 1 && got == t)      Serial.println("Self-test: OK (eko mottaget)");
  else if (n == 1)             { Serial.print("Self-test: eko avvek 0x"); Serial.println(got, HEX); }
  else                         Serial.println("Self-test: INGET eko — kolla TX/RX/transceiver/pull-up/12V");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n== Td5 K-Line bring-up (ESP32 UART2 16/17, 10400 8N1) ==");
  Serial2.begin(KLINE_BAUD, SERIAL_8N1, PIN_KRX, PIN_KTX, KLINE_INVERT);
  delay(50);
  klineSelfTest();
  Serial.println("Skicka valfritt tecken i seriemonitorn for fast init + StartCommunication.");
}

void loop() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    Serial.println("\n-- fast init + StartCommunication --");
    klineFastInit();
    startCommunication();
  }
}
