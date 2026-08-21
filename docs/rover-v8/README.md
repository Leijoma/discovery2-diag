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
| **Thor / Bosch (Motronic)** | late V8 (Disco 2 V8, P38 late, Defender) | K-line, ISO 14230 **KWP2000** | **Closest to our Td5 work** — fast init, KWP2000 services, negative responses. Our K-line/KWP2000 layer should largely carry over. |

## Why this is realistic

The bottom three layers of our stack — transport, K-line framing/init, KWP2000 — are
**vendor-neutral** (see [../discovery-2-td5/kline-protocol.md](../discovery-2-td5/kline-protocol.md)).
A new engine family is mostly a new **module profile**: address, init type, LID map,
optional seed→key, and fault tables. Thor/Bosch V8 (KWP2000 over K-line) is the
natural next target because it reuses the most.

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
