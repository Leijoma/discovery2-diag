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

### WiFi and uplink (2026-11-12)

Three networks in priority order: home (`WIFI_SSID_1`) → the Pi's AP (`WIFI_SSID_CAR`,
`Discopi`) → phone hotspot (`WIFI_SSID_2`). The node boots in seconds and the Pi in about 30 s,
so the Pi's AP is usually missing at boot. `wifiTick()` handles that without blocking the
K-line: with no link it runs an async scan every 15 s; on the phone it scans every 60 s and
moves up to `Discopi`; on `Discopi` it looks for home every 5 min. A failed move-up bans that
network for 10 min. The old boot-time list walk blocked `loop()` for 8 s per network.

- **On `Discopi`** Influx writes go to the Pi's store-and-forward relay
  (`RELAY_URL`, default `http://192.168.4.1:8086`, same `/api/v2/write` API), and NTP asks
  `192.168.4.1` first. Everywhere else they go straight to `INFLUX_URL` over WG, so a missing
  Pi never costs data. The relay must answer 204 only after the line is on disk, because
  read-and-clear erases on that 204. The spec is in the head unit repo,
  `HANDOVER-kline-relay.md`.
- `/data` has `net` (`home|car|phone|none`), and the `node` heartbeat has `net` (0–3).
- `/wifi?use=car|home|phone|auto` pins a network until reboot, so the relay can be tested
  indoors. Its `ev` field is a short roaming log (scans, joins, bans). It is there because the
  serial log can't be read in the field: opening the USB port resets the ESP.
- **Scan timeout (core 2.0.17).** `scanNetworks()` sets the async scan timeout to 20 × the
  per-channel time and checks it before the done bit. A scan made while connected takes
  3.5–6+ s, so the default made every scan from home or the phone fail, and the node never
  moved up to `Discopi`. The node therefore sets a 30 s timeout after each start (see
  `ScanTimeout`).

### Demo mode

`/demo?on=1|0`, or **Demo data** in Settings. It is RAM-only, so a reboot or reflash ends it.
It runs a synthetic 120 s drive (idle, 0–90 km/h, cruise, brake). Coolant warms up over 5 min,
and TD5 fault bit 0 is on for 20 s of each cycle. Values go through the same
`appendField`/`appendFuel` path as real data, so `/data` and the Influx line have the real
shape, but the lines are tagged `vehicle=demo` and are never spilled. Demo mode stays off the
K-line. The `node` heartbeat says `demo=1i`, and the live page shows a DEMO badge. Use it to
test a display (the Pi's Car pane) without the car. With `/wifi?use=car` it goes through the
relay, which keeps the latest point per (measurement, vehicle) for the head unit.

### Fuel

Every `engine` line, real or demo, carries the on-node fuel computer. It uses the same math as
the Python `_FuelComputer`:

| field | unit | meaning |
|---|---|---|
| `fuel_rate` | L/h | instantaneous, from injection quantity × rpm (also at idle) |
| `economy` | L/100 km | instantaneous, only above 5 km/h |
| `trip_economy` | L/100 km | average since start, once 0.1 km has been driven |
| `trip_fuel` | L | burnt since start |
| `trip_km` | km | driven since start |
| `trip_min` | min | since the first fuel sample |
| `trip_avg_kmh` | km/h | average speed since start, after 30 s |

"Start" means the node booting, which happens when the key is turned on, since the node is fed
from accessory power. Demo on also counts as a start. The trip totals are sent every cycle, so a
display that comes up late still gets the whole trip.

The heartbeat also carries `bridge`, `ign_cycle` and `logging` (ints), so a reader of the
pushed lines needs nothing from `/data`. It beats from the main loop, so it keeps beating while
muted and in demo, and it beats at once on a demo, mute or cable-mode toggle. In cable mode the
node doesn't beat, except for one `bridge=1i` beat when cable mode is entered from the web.

### SLABS read-and-clear at start

On by default (Settings → **SLABS clear at start**, `/slabsclear?on=1|0`, persisted). At the
first successful standstill SLABS sample of each ignition cycle, the node:

1. stores the logged block `21 11` as `slabs_clear.flog_before`, and goes on only once it is
   stored: Influx (or the Pi relay) answered 204, or the line is in the flash spill. Never
   erase what isn't stored;
2. sends ClearFaults `14 FF FF` and waits for the late `54` (~300 ms, EEPROM write);
3. re-reads `21 11` → `slabs_clear.ack`, `flog_after`, `nflog_after`.

So each start records what the **previous** drive latched (B-011: `020` alone = 3 amigos, `027`
= 4). It is the only write the node makes to SLABS. Switch it **off before a workshop visit**,
because a cleared log shows them only the last drive, and the per-code counters are gone.

**The window is short.** SLABS answers only until the car first moves after an ignition cycle.
So the first SLABS sample runs before the TD5 session, about 12 s after boot. Until one
succeeds, the node retries every 10 s at a standstill, until the car has moved. Once the car
has moved there are no more SLABS samples this cycle: SLABS refuses them anyway, and each failed
try froze live data for ~7 s at every stop. The old fixed
60 s after boot missed the window on both drives of 2026-11-14. `slabs_rd` in the heartbeat and
`/data` shows how far it got this cycle: 0 not read, 1 read, 2 read + cleared. When cycling the
ignition at a stop, stand still until it is ≥ 1.

**Without a clock.** The node boots with no clock (KL15 power) and gets NTP only once the uplink
is up. A line spilled before that carries ` @<boot>:<ms>` instead of an epoch, and gets its epoch
when it is flushed in the same boot. From an earlier boot, `slabs*`/`mark` lines go without a
timestamp (Influx stamps them on arrival), and engine/node lines are dropped. The boot counter is
in NVS (`boots`).

**Engine lines and beats wait for the clock (2026-11-22).** With no clock, these go straight to the
spill instead of being posted unstamped. Only the relay paths (`Discopi`, USB) work without a
clock, and there an unstamped line only lands in quarantine. So in the car the node buffers while
the Pi boots and finds its GPS fix. The Pi's `@T` (or NTP) then sets the clock, the backlog flushes
with real timestamps, and the relay stores everything until it has an uplink. Data is lost only if
the ignition goes off before the Pi has a fix.

**WG never blocks the loop.** `wgStart()` asks for NTP and returns at once if the clock isn't
set. `loop()` retries every 5 s and brings the tunnel up once it is. It used to wait up to 8 s
for NTP, retried every 30 s, and on `Discopi` (no NTP answer) that froze live data for 9 s every
30 s: the dropouts seen on the Pi's Car pane on 2026-11-17. `setup()` waits at most 3 s, and only
when WiFi is already up.

**`reset=wdt` in the heartbeat is usually a power dip, not a hang.** On 2026-11-14 it came at
engine cranking with ignition on (11.8 V), and the other `wdt` boots line up with short ignition
cycles at a stop. A clean power-off gives `poweron`. Both mark an ignition cycle in the data, **but
not always**. On 2026-11-21 (second drive) the node gave five `wdt` boots while driving at 20–75 km/h
with the engine running (18:48:48, 18:57:37, 18:58:50, 19:02:21, 19:04:56Z), so a `wdt` boot is not
proof of an ignition cycle. `ESP_RST_WDT` is the RTC/other watchdog, not `task_wdt`/`int_wdt`/`panic`,
which points at a supply interruption rather than a software hang. The driver then found a loose
contact in the USB charger that feeds the node, which matches.

### USB uplink to the Pi (2026-11-22)

The node can be powered from a USB port on discopi. The same cable then carries its Influx writes
and the Pi's GPS time, so the car needs neither WiFi nor NTP, and the loose-charger resets of
2026-11-21 go away. WiFi stays as the fallback. The protocol uses the cable-mode port (115200 8N1,
`\n`-terminated). The Pi's lines start with `@`, so they never collide with the cable-mode
commands or the debug prints:

| direction | line | meaning |
|---|---|---|
| Pi → node | `@T <epoch>` | keep-alive every ~5 s. The epoch is sent only while the Pi's clock is synchronised (GPS/chrony), otherwise `@T 0` |
| Pi → node | `@A <seq>` | everything since the previous `@E` is committed to the relay's disk |
| node → Pi | `@L <line>` | one line-protocol line, `precision=s`, the same as the HTTP body |
| node → Pi | `@E <seq>` | end of one write |

- **The node uses USB first.** It does so when it has heard any `@` line within 15 s. With no
  `@A` within 1.5 s, it marks the host as gone until the next `@T`, and the write goes over WiFi
  or to the flash spill.
- **`@A` must mean what the relay's 204 means** (the lines are on disk), because the SLABS
  read-and-clear erases on it.
- **`@T`:** the node steps its clock only when it is unset or more than 2 s off.
- **The heartbeat and `/data` carry `usb` (0/1).** The Pi stamps lines that have no timestamp on
  arrival, the same as on the HTTP path.
- **Opening the port must not reset the ESP.** The DTR/RTS auto-reset would reboot the node
  ~30 s after key-on, in the middle of the SLABS window. Use a **plain**
  `serial.Serial(path, 115200)`. The kernel raises DTR and RTS together on open, and HUPCL drops
  them together on close, so EN never goes low. Do **not** set `dtr=False`/`rts=False` before
  `open()`: pyserial applies them one at a time, and the moment when DTR≠RTS *is* a reset. The Pi
  agent measured this on 2026-11-22: three opens gave three boots that way, and four plain opens
  gave none.
- **Cable mode still works over the same port.** A host that wants the K-line sends the bridge
  commands (`PING`, `INIT`, …), and the node stops logging until it goes idle. The Pi then has to
  stop the uplink while it does.
- **Flashing over the Pi:** `esp32/flash_via_pi.sh <pio build dir> [--full]`. It copies the image
  to discopi and runs esptool under `/data/kline-relay/node-port`, which takes the port from the
  relay and hands it back afterwards. It writes `boot_app0.bin` too, because after an OTA update
  the node boots from app1, and writing only 0x10000 would be ignored. Tested 2026-11-22 (app only,
  17 s at 460800 baud). An esptool hard reset reports `reset=poweron`. OTA over WiFi still works.

### Amigos mark

The **Amigos** chip in the live page's header (or `/mark?lamps=3|4|0`) writes
`mark,vehicle=RDL016,src=node amigos=1i,lamps=<n>i`, spilled if the uplink is down. In demo mode
it is tagged `vehicle=demo`. The Pi's Car pane writes the same line with `src=pi` into its relay.
The lamps stay lit until the next ignition cycle, so only the first onset per cycle can be marked.
The per-segment SLABS read-and-clear above tells which code latched (test plan T-24).

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
