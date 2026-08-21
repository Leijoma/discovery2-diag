# ESP32 — K-Line

Firmware for Td5 diagnostics directly from an ESP32 (alternative to Pi + USB KKL).

## kline_test/

Bring-up sketch. UART2 on **GPIO16 (RX)** / **GPIO17 (TX)**, 10400 8N1.

**Requires a K-Line transceiver between the ESP32 and the K-line (12 V)** — e.g. L9637D.
Never connect 12 V directly to the ESP32 pins. Assumes a non-inverting transceiver;
set `KLINE_INVERT = true` in the sketch if your interface inverts.

Runs a self-test at boot (sends a byte, checks the transceiver's echo — requires the
K-line side to be powered with 12 V + pull-up). Then send any character in the serial
monitor (115200) to run fast init + StartCommunication
(`81 13 F7 81 0C`) and print TX/ECHO/RX in hex.

### Flash

Arduino IDE: select your ESP32 board + port, open `kline_test/kline_test.ino`, upload.
Open the serial monitor at 115200.

Or `arduino-cli`:

```
arduino-cli compile -b esp32:esp32:esp32 esp32/kline_test
arduino-cli upload  -b esp32:esp32:esp32 -p <PORT> esp32/kline_test
```
