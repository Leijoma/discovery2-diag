# Scope & architecture

**The core mission of this project is communication with the car and interpretation of
its data.** Storage and presentation (dashboards, logging, InfluxDB/Grafana) are useful,
but they are *consumers* built on top of the core — not the point of it. This file states
that boundary so the extras don't quietly become the product.

## Three layers, one contract

```
COMMS  — talk to the ECUs over K-line (platform-specific; same protocol, two impls)
  Python:  transport/ · kline/ · kwp2000/ · session.py · ports.py
  ESP32:   the C firmware in esp32/ (fast init, KWP2000, seed→key, LID reads)
        │  raw LID bytes
        ▼
INTERPRETATION  — turn raw bytes into named, scaled, confidence-tagged signals
  signals/*.json = the SINGLE SOURCE OF TRUTH (offset / scale / unit / confidence)
  the module decoders (td5/ slabs/ airbag/ bcu/ ace/ autobox/) read it
  Python decodes it at runtime; the ESP consumes a header generated from the same JSON
        │  normalized snapshot: {status, signals:[{name,value,unit,confidence,status}], faults:[]}
        ▼ ───────────────── the defined API (the contract) ─────────────────
CONSUMERS  — storage & presentation (optional, swappable)
  web/ dashboard + SSE · file logging · InfluxDB/Grafana · raw-log collector · community upload
```

**Core = COMMS + INTERPRETATION** (the top two layers). Everything below the snapshot
contract is optional and replaceable.

## The one hard rule

**Core never imports from the consumer layer.** `transport`, `kline`, `kwp2000`,
`session`, `ports`, the module decoders and `signals` must not import from `web` (or any
future storage/presentation package). Data flows one way: comms → interpretation →
snapshot → consumers. `web/sources.py` is the boundary — it consumes the core and adapts
it for the UI.

## Two platforms, one interpretation

K-line comms are offered both from a computer (Mac/PC/Pi + a KKL cable, in Python) and
from an ESP32 (firmware). The protocol is necessarily implemented twice (C and Python
can't share code), **but interpretation is not duplicated**: `signals/*.json` is the one
contract. The ESP's decode table is *generated* from it, never hand-copied — hand-copying
is exactly what caused the MAF mis-map (the store and the ESP drifted apart).

## What lives where

- `src/d2diag/` — the core library (comms + interpretation) plus, under `web/`, the
  reference consumer (dashboard/SSE/logging).
- `esp32/` — the ESP32 firmware (a second comms node).
- `tools/` — CLI + reverse-engineering utilities (`raw_analyze`, `lid_sweep`, `verify_ecu`,
  `export_signals`, `dashboard`, …).
- `signals/*.json` — the interpretation contract; written only via `upsert_field`.
- `references/` + `docs/` — protocol knowledge; `references/test_plan.md` is the living
  car-test backlog.
- InfluxDB / Grafana / the raw-log collector live on a separate server, not in this repo.

## Deliberately out of scope (for now)

- Splitting the repo into a standalone core library + a separate hub repo. The layering is
  enforced *inside* this repo first; a physical split is a later step if it earns its keep.
- The car's own faults and maintenance history — those belong in the sister project
  `../Discovery 2/`, not here.

See `CLAUDE.md` for the detailed layer-by-layer stack and the hard-won protocol rules.
