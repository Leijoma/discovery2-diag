# Rover V8 platforms — roadmap (not started)

Placeholder for extending this knowledge base to the **Rover V8** engine-management
families found in Discovery 1/2, Range Rover Classic/P38, and Defender. Nothing here
is verified yet — this page exists to frame the work and collect pointers.

Confidence tags: 🟢 Proven · 🟡 Assumed · 🔴 Unknown ([legend](../README.md)).
Everything below is currently 🔴.

## The three eras

| System | Era / fitment | Interface | Notes |
|---|---|---|---|
| **Lucas 14CUX** | early Rover V8 EFI (RR Classic, Disco 1, Defender) | serial memory-read protocol (**not** KWP2000) | No seed/key, no `21 xx`; reads ECU RAM directly. Reference: `colinbourassa/libcomm14cux` (protocol facts only). |
| **GEMS** | mid-90s V8 (Disco 1, P38, RR Classic late) | K-line, ISO 9141-2 | 5-baud slow init; simpler command/response than KWP2000. |
| **Bosch Motronic M5.2.1** | Disco 2 V8 1999–2004, P38 4.0/4.6 1999–2002 | OBD port; bus and init **unknown** (see below) | Probably the closest to our Td5 work, if it turns out to be K-line/KWP2000. Unproven. |

## Bosch Motronic M5.2.1: what is known (2026-11-25)

Everything is 🟡 or 🔴. Nothing has been read on a car by us yet.

- 🟡 **Fitment.** Discovery Series II 1999–2004 and Range Rover 38A 1999–2002, per Land Rover's
  own on-board diagnostics document for the M5.2.1, and Lynx's coverage list (which keeps it
  separate from the earlier GEMS). No other model uses it, so a Disco 2 V8 profile is also a
  late-P38 profile.
- 🟡 **Generic OBD-II.** The same Land Rover document covers it for OBD. Owners report reading
  engine codes with ELM327 + Torque, with mixed results ("cannot connect to ECU" for some).
  Which generic protocol it uses (ISO 9141-2 or ISO 14230) is not stated anywhere we found.
  🟢 **Confirmed by a community report** (GitHub issue #2, D2 4.0 V8): a self-built WiFi ELM327
  tool read the engine code **P1590**, the generic "rough-road signal" fault that the ECU sets
  when SLABS reports an ABS problem. So generic OBD reaches the M5.2.1. The protocol the ELM327
  picked was not reported.
- 🔴 **Land Rover-specific channel** (what Testbook/Nanocom/Lynx/Faultmate use for live data
  and adaptations). There is no open source for the address, init, services or LID map. Other
  Bosch ECUs use 0x10/0x11/0x01 (VAG ME7), but that is not evidence for this ECU.
- 🔴 **BMW DS2.** BMW owned Rover when the M5.2.1 was developed, and BMW's own M5.2 (M62 V8)
  talks DS2. This is only an idea, but it is cheap to test.
- 🟡 **The rest of the car is shared.** SLABS, the airbag module (SRS) and the BCU are the same
  modules on the V8 and the Td5, so those parts of this project apply as they are. The gearbox
  (EAT) talks to the engine ECU over CAN; how it is diagnosed is a separate question.

**First step:** [`tools/v8_probe.py`](../../tools/v8_probe.py) (test T-26 in
`references/test_plan.md`). It tries a 5-baud init at 0x33, a functional fast init at 0x33,
physical fast inits at 0x10/0x11/0x12/0x01 and DS2. All of it is read only.

Sources:
- Blackbox Solutions, M5.2.1 product page: https://blackbox-solutions.com/shop/product/sm009
- Lynx coverage leaflet: https://rimmerbros.com/ItemFiles/Manuals/lynx_leaflet.pdf
- Faultmate MSV-2 on a 1999 P38 4.6 (Thor): https://stockholmviews.com/p38/faultmate-review.html
- Owner reports, Torque/ELM327 on a D2: https://landroverforums.com/forum/discovery-ii-18/torque-app-android-review-42985/page2
- ME7 fast-init addresses (not M5.2.1): https://github.com/NefMoto/NefMotoOpenSource/issues/123

## Why this is realistic

The bottom three layers of our stack — transport, K-line framing/init, KWP2000 — are
**vendor-neutral** (see [../discovery-2-td5/kline-protocol.md](../discovery-2-td5/kline-protocol.md)).
A new engine family is mostly a new **module profile**: address, init type, LID map,
optional seed→key, and fault tables. Thor/Bosch V8 (KWP2000 over K-line) is the
natural next target because it reuses the most, provided the probe confirms K-line/KWP2000.

## What's needed (each 🔴, help wanted)

- A Thor/GEMS/14CUX vehicle to sniff, or factory-tool traces.
- The `21 xx` (or memory-address) live-parameter map per system.
- Fault-code tables and clear routines.
- For 14CUX: the RAM layout (different paradigm — direct memory read, not services).

## Pointers

- `colinbourassa/libcomm14cux` — 14CUX serial protocol (petrol V8, raw memory read).
- `colinbourassa/memsgauge` / `librosco` — Rover MEMS (4-cyl K-series, ISO 9141-ish) —
  useful as a K-line/FTDI wiring and handshake reference, not V8-specific.
- Generic KWP2000/ISO 14230 libraries for the Thor init sequence.

> Have a Rover V8 and a K-line cable? The fastest way to start is a passive sniff of a
> factory tool session — open an issue and we'll help structure the capture.
