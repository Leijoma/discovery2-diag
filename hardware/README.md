# Standalone ESP32 K-line diagnostic tool — hardware

A small ESP32 board that plugs into the OBD-II port, is powered from it, and talks
K-line (read **and** write) to the vehicle's control modules. CAN is prepared as a
future add-on (the D2 Td5 doesn't use CAN; other vehicles do). Designed to survive
the automotive environment: voltage spikes / load dump, reverse polarity, brown-out.

> ⚠️ **Never connect 12 V directly to an ESP32 pin.** The L9637D transceiver and the
> buck regulator sit between the 12 V bus and the 3.3 V logic. Bench-test everything
> from a **current-limited** 12 V supply (~200 mA) before plugging into the car.

This documents the design and BOM. Firmware bring-up reuses
[`esp32/kline_test.ino`](../esp32/kline_test.ino); the transceiver circuit follows
the ST reference used in
[`references/muki01_OBD2_K-line_Reader/Schematics/L9637D.png`](../references/muki01_OBD2_K-line_Reader/Schematics/L9637D.png).

## OBD-II pins used (D2 Td5)

| OBD pin | Signal | Use |
|---|---|---|
| 7 | K-line | ISO 9141 / ISO 14230 (KWP2000) — the one data wire |
| 4 | Chassis GND | ground |
| 5 | Signal GND | ground (tie to pin 4) |
| 16 | Battery +12 V | **constant** (unswitched) — power in |
| 6 / 14 | CAN-H / CAN-L | **future add-on only** (unused on D2 Td5) |

K-line idles **HIGH at ~12 V**, single wire, half-duplex, **10400 baud 8N1**; every
transmitted byte echoes back and must be swallowed by the firmware.

## Block diagram

```
OBD16 +12V ─ PTC fuse ─ reverse P-FET ─ TVS(load dump) ─┬─ wide-Vin buck → 3.3V ─→ ESP32
                                                        └─ 12V → L9637D VS (via diode)

OBD7 K ── 510Ω pull-up→12V ── L9637D "K" (pin6)     L9637D: RX(1)→GPIO16, TX(4)→GPIO17
OBD4/5 GND ── common ground                         L9637D: VCC(3)=3.3V, GND(5), VS(7)=12V
OBD6/14 CAN ── [DNP] SN65HVD230 ── TWAI GPIO4/5      (future, not populated)
```

## 1. Power & input protection (12 V → 3.3 V)

Robustness against spikes is the priority here (ISO 7637 load dump on an old vehicle
can reach ~35–40 V).

- **PTC resettable fuse** in series on 12 V (~500 mA hold / 1 A trip). Protects both
  the board and the car's OBD circuit.
- **Reverse-polarity protection:** high-side P-channel MOSFET (low loss). Add a
  gate-source resistor + a 12–15 V zener across gate-source to protect the gate from
  transients. (Simpler alternative: a series Schottky, ~0.4 V drop.)
- **Load-dump TVS:** unidirectional, standoff ~24 V, across 12 V after the fuse
  (clamps ~39 V). Clamps the transient before it reaches the buck.
- **Input bulk:** 100 µF electrolytic + 100 nF ceramic.
- **Buck regulator → 3.3 V @ 500 mA:** choose a **≥40 V input** part for load-dump
  margin. Final: LMR14030 (40 V) or similar. Prototype: an **LM2596HV module (60 V
  in)** is fine; an MP1584 module (28 V max) works **on the bench behind the TVS
  only** — too little margin for a real vehicle transient.
- **3.3 V rail:** 470 µF low-ESR bulk close to the ESP32 (WiFi TX bursts draw ~½ A
  peaks) + 100 nF decoupling.

> ⚠️ **"Always powered" caveat.** OBD pin 16 is unswitched battery — the ESP32
> (~80–150 mA with WiFi) will flatten the battery over days. Add a **physical power
> switch** or use deep-sleep + wake, and/or unplug when parked. Enable the ESP32
> brown-out detector so a starter-motor crank dip doesn't corrupt anything.

## 2. K-line transceiver — ST L9637D

Follows the muki01 `L9637D.png` reference. Pinout (SO-8):

| Pin | Name | Connect to |
|---|---|---|
| 1 | RX | ESP32 **GPIO16** (UART2 RX) |
| 2 | LO | L-line out — **not used** (leave open) |
| 3 | VCC | **3.3 V** logic supply (see note) |
| 4 | TX | ESP32 **GPIO17** (UART2 TX) |
| 5 | GND | ground |
| 6 | K | OBD **pin 7**, with **510 Ω pull-up to 12 V** |
| 7 | VS | **12 V** via a series diode (1N4148/1N4007) + 100 nF decoupling |
| 8 | LI | L-line in — **not used** (tie per datasheet / leave) |

- ⚠️ **VS is pin 7, LI is pin 8** (confirmed against the ST datasheet + the muki01
  schematic). Some secondary/third-party sheets mis-number these — during bring-up a
  paper claimed VS on pin 8; wiring 12 V there leaves the real VS (pin 7) unpowered
  and the K driver dead (symptom: RX stuck high, no echo). Go by pin 1 = the dot/notch.
- **510 Ω K-line pull-up** to 12 V (use **0.5 W** — it dissipates ~0.28 W when the
  line is pulled low). Add a small **series R (~100 Ω) + a TVS/zener clamp** on the
  K node for extra surge margin (belt and suspenders; the L9637D is already ~40 V
  tolerant).
- ⚠️ **Pull-up value is critical for bit timing.** It sets the K rise time (τ = R·C).
  At 10400 baud a bit is only **96 µs**, so R must be small: **510 Ω–1 kΩ**. A
  too-high value garbles the transmitted bytes *even though the DC line-diag passes* —
  bring-up 2026-08-23 accidentally used **470 kΩ**: line-diag OK, but the echo was
  corrupt at 10400 and only clean at 2400 baud. Swapping to **1 kΩ** fixed it instantly.
  (On the car the ECU's own pull-up helps, but include your own 510 Ω–1 kΩ.)
- The L9637D is **non-inverting** → `KLINE_INVERT` is **false** (now the default in
  `kline_test.ino`); `klineLineDiag()` confirms it ("loop closes, non-inverted").
- **L-line not needed** for the Td5 (both fast init and 5-baud slow init run on K).

> ⚠️ **VCC = 3.3 V note.** The L9637D is spec'd around 5 V logic but commonly works
> at 3.3 V, which keeps the RX output (pin 1) within the ESP32's 3.3 V limit. Verify
> the RX idle level with the line-diag. **If you must run VCC at 5 V**, add an RX
> divider down to ≤3.3 V *and* check that the ESP32's 3.3 V TX still meets the
> L9637D's VIH (≈0.7·VCC) — otherwise level-shift TX too.

## 3. ESP32-WROOM-32 + pin map

| GPIO | Function | Net |
|---|---|---|
| 16 | UART2 RX | ← L9637D pin 1 (RX) |
| 17 | UART2 TX | → L9637D pin 4 (TX) |
| 4 | TWAI TX | → CAN transceiver (future, DNP) |
| 5 | TWAI RX | ← CAN transceiver (future, DNP) |
| EN / IO0 | reset / boot | buttons + auto-reset on PCB |

- **Prototype:** use an ESP32-DevKitC (on-board USB-UART + auto-reset). Power its
  3V3 pin from the buck (or power the devkit from the buck's 5 V if you add a 5 V tap).
- **PCB version:** USB-C + CP2102N or CH340C on UART0 (GPIO1/3) with the classic
  DTR/RTS→EN/IO0 auto-reset, plus BOOT + EN buttons. Keep strapping pins
  (IO0/IO2/IO12/IO15) in safe boot states.

## 4. CAN — future add-on (footprint only, DNP)

- **SN65HVD230** (3.3 V CAN transceiver) on TWAI pins GPIO4 (TX) / GPIO5 (RX), to
  OBD pin 6 (CAN-H) / pin 14 (CAN-L).
- **120 Ω termination via a jumper, default DNP** — a diagnostic tool should not
  normally terminate a live bus (it already has 2×120 Ω).
- Not populated until a CAN vehicle is on the bench.

## Bill of materials (prototype)

| Ref | Part | Value / spec | Purpose | Example |
|---|---|---|---|---|
| U1 | **ST L9637D** | SO-8, K-line/ISO 9141 xcvr | K-line front-end | Farnell **E-L9637D** (+ SO-8→DIP breakout for breadboard) |
| U2 | ESP32-WROOM-32 | DevKitC (proto) | MCU + WiFi | any ESP32 devkit |
| U3 | Buck module | ≥40 V in → 3.3 V, ≥0.5 A | 12 V → 3.3 V | LM2596HV module (proto) / LMR14030 (PCB) |
| F1 | PTC fuse | 500 mA hold / 1 A trip | overcurrent | Bourns MF-R050 |
| Q1 | P-MOSFET | ≥40 V, low RDS(on) | reverse polarity | AO3401A / DMP3098L |
| D1 | TVS | 24 V standoff, unidirectional (SMB) | load-dump clamp | SMBJ24A |
| D2 | Diode | 1N4148 (or 1N4007) | L9637D VS feed | 1N4148 |
| D3 | TVS/zener | ~16–24 V on K node | K-line surge | SMBJ16A + series R |
| R1 | Resistor | **510 Ω, 0.5 W** | K-line pull-up to 12 V | — |
| R2 | Resistor | ~100 Ω | K-line series (surge) | — |
| Rgs/Zg | 100 kΩ + 12–15 V zener | P-FET gate protection | — |
| C1 | Cap | 100 µF electrolytic | input bulk | — |
| C2 | Cap | 470 µF low-ESR | 3.3 V bulk (WiFi) | — |
| C3–5 | Cap | 100 nF ceramic | decoupling (VS, VCC, rail) | — |
| J1 | OBD-II male | connector / pigtail | vehicle interface | OBD-II male to flying leads |
| — | Enclosure | small box / OBD-plug shell | — | — |

**CAN add-on (DNP):** SN65HVD230 (SO-8), 120 Ω 0.25 W (jumper), pin header.

## Firmware

- **Bring-up now:** [`esp32/kline_test.ino`](../esp32/kline_test.ino). Sequence:
  `klineLineDiag()` (confirm non-inversion with the L9637D → set `KLINE_INVERT=false`)
  → `0xA5` self-test (needs 12 V + pull-up present) → fast init → Td5
  StartCommunication `81 13 F7 81 0C` → expect **`C1 57 8F`**.
- **Architecture decision deferred** (hardware is identical either way):
  - **WiFi bridge (least work, reuses everything):** extend the firmware into a TCP
    server + a small control protocol (`fast_init` / `slow_init` / `set_baud`, then
    transparent bytes). Add a thin `src/d2diag/transport/tcp_transport.py` that maps
    those control calls to messages and `send`/`receive` to the socket. The existing
    `SerialTransport` already opens `serial_for_url("socket://…")`, so only the
    control methods are missing — the whole `d2diag` stack + dashboard then run
    unchanged on a host (Pi/laptop).
  - **Fully standalone C (true plug-and-phone):** port the KWP2000/Td5 layers + a web
    server to the ESP32. Large effort — defer until the hardware is proven.

## Build & verification phases

1. **Breadboard.** ESP32 devkit + buck module + L9637D (on SO-8→DIP) + 510 Ω / diode
   / 100 nF, fed from a **current-limited bench 12 V (~200 mA)**.
   Verify: 3.3 V rail stable · ESP32 boots · `klineLineDiag` healthy (correct
   inversion) · `0xA5` self-test echoes (with 12 V + pull-up).
2. **Against the car.** ✅ **VERIFIED 2026-08-23** (breadboard: ESP32-DevKitC + L9637D
   on SO-8→DIP, VCC 3.3 V, 12 V + **1 kΩ** pull-up, in the car): fast init returned
   **`03 C1 57 8F AA`** from the Td5 (KW 57 8F, checksum OK) — matches the car sniffs.
   Self-test echoed clean and line-diag showed "loop closes, non-inverted".
   Next: a `21 xx` read, cross-check vs USB-KKL + d2diag; SLABS fast init at 0x29.
3. **Perfboard in an enclosure** with an OBD pigtail; run in the car; verify stability
   and no resets on starter crank (brown-out).
4. **PCB (KiCad → JLCPCB):** protection + CAN footprint DNP, OBD-plug format. Ties into
   the distribution goal in [`../TODO.md`](../TODO.md) (hardware for others).

## Known risks / open decisions

- **Load-dump margin** — final buck must be ≥40 V input (MP1584 bench only).
- **Inversion** — L9637D is non-inverting → flip `KLINE_INVERT` to `false`; confirm
  with line-diag before trusting fast init.
- **L9637D VCC at 3.3 V** — verify RX idle level; level-shift if you run VCC at 5 V.
- **Battery drain** — unswitched OBD 12 V needs a switch / deep-sleep.
- **Firmware architecture** — WiFi bridge vs standalone C; decide once hardware is proven.
