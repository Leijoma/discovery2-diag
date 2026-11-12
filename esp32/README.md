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


## kline_node/

The full node: WiFi/OTA/web + the K-line engine + Influx spill. Its web UI has a
**Silence bus** toggle (`/log?on=0`) to hand the shared K-line to another master — a
USB-KKL cable, a Nanocom — without power-cycling the ESP.

### Sharing the bus — mute the right way

K-line is a single shared wire (pin 7). Two masters must never drive it at once, so
before another tool can use it the node has to get **off** — and getting off is not just
"stop sending".

> **Rule: mute = release the link (`82`) -> then hold TxD idle.**

A fast init opens a *communication link* that outlives silence. If the node just stops
polling with that link still open, the other tool's StartCommunication is met with
`7F 81 10` (generalReject) — the exact bug chased and fixed in
`references/slabs_protocol.md` ("a `7F 81 10` on StartCommunication means a link is still
open"). So on mute the node sends **StopCommunication `82`** once (`stopComm()` ->
`01 82 83`) to tear the link down cleanly, then stays off the bus. This is already what
the Silence-bus toggle does (`handleLog()` in `kline_node.ino`); on resume it re-clears
and re-establishes.

### SLABS hold (fault-order test)

Settings → **SLABS hold** (`/slabshold?on=1|0`, persisted in NVS) switches the node from engine
logging to holding **one SLABS session** through a drive. That session is what can catch the
SLABS *current* faults (`21 47`) while the warning lamps are lit; see `references/test_plan.md`
T-23 for why and for the decision rule. It must be switched on at a standstill right after an
ignition cycle, because SLABS won't accept a new connection once the car has moved. In this mode:

- No TD5 data at all. The bus is SLABS-only, at one request/s (`21 47` every 2 s, bare `3E` +
  `21 43` every 4 s, `21 11` about every 32 s).
- Influx `slabs_fault` (tags `block`=cur|log, `bit`) is one point per bit edge: `state`, `seq`
  (poll counter, orders edges within one second), and `base`=1 for bits already set at connect.
- Influx `slabs_hold` has `alive`, `up_s` (how long the session has lived), and raw `w43`/`fcur`
  about every 12 s, plus `alive=0` the moment the session dies.
- Points are spilled to flash when the uplink is down, the same as `engine`.

### Practical TODOs (mute / bus-sharing)

- [ ] **Listen-before-talk.** Before fast init (and before resuming from mute), sniff the
      line briefly; if another master's init pulse or frames are heard, back off and retry
      later. Automatic protection on top of the manual mute — stops a race if someone
      starts the KKL tool without pressing Silence first.
- [ ] **Passive sniff while muted.** While silenced the node hears everything the other
      tool does. Decode those frames read-only and learn LIDs/values for free (feeds the
      same differential mapping as `sniff/automap.py`). Turns idle mute time into data.
- [ ] **Confirm the `82` lands before yielding.** `stopComm()` fires once and does not
      check for the `C2` ack; a dropped `82` would leave the link half-open again. Read
      the reply (or send it twice) so mute is reliable even on a noisy turnaround.
