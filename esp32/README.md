# ESP32 — K-Line

Firmware för Td5-diagnostik direkt från en ESP32 (alternativ till Pi + USB KKL).

## kline_test/

Bring-up-sketch. UART2 på **GPIO16 (RX)** / **GPIO17 (TX)**, 10400 8N1.

**Kräver en K-Line-transceiver mellan ESP32 och K-line (12 V)** — t.ex. L9637D.
Koppla aldrig 12 V direkt till ESP32-pinnarna. Antar icke-inverterande transceiver;
sätt `KLINE_INVERT = true` i sketchen om din interface inverterar.

Gör vid boot en självtest (skickar en byte, kollar transceiverns eko — kräver att
K-line-sidan är matad med 12 V + pull-up). Skicka sedan valfritt tecken i
seriemonitorn (115200) för att köra fast init + StartCommunication
(`81 13 F7 81 0C`) och skriva ut TX/ECHO/RX i hex.

### Flasha

Arduino IDE: välj din ESP32-board + port, öppna `kline_test/kline_test.ino`, ladda upp.
Öppna seriemonitorn på 115200.

Eller `arduino-cli`:

```
arduino-cli compile -b esp32:esp32:esp32 esp32/kline_test
arduino-cli upload  -b esp32:esp32:esp32 -p <PORT> esp32/kline_test
```
