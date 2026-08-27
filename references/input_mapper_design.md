# Interactive input mapper — design (plan before code)

Status: **design only, not built.** This document is the plan for a guided tool that turns
*documented names* into *proven bits* by differential mapping on a live bus. Decide the open
questions here before writing code.

## Why

Several modules expose switch / input / settings LIDs whose **names** are documented but whose
**raw `LID:byte.bit` mapping** is not:

- **BCU** inputs `21 D8`–`21 E9`, `21 2C`/`21 2D`, and the undocumented block `21 20`–`21 29`;
  settings `21 C6`–`21 EB` (see `valeo_bcu_capabilities.md`).
- **TD5** switch bitfields `21 1E`/`1F`/`20`/`36` (see `td5-input-lids-decode`).
- **SLABS** switch/valve bits.

Turning a documented name ("driver door switch") into a stored signal needs a differential map:
capture a baseline, toggle the physical input, diff the bytes. Done by hand on a *live* bus this
is error-prone — counters, voltages and timers change on their own and drown the real bit. This
tool **guides** the toggle loop and **de-noises** the diff, then writes confirmed bits to the
signal store as `kandidat`. It is module-agnostic: any bitfield LID on any module.

## Interaction models (we want both)

### A. Wiggle-watch — discovery
A live bit-matrix on screen. The operator physically toggles something (open/close a door, turn
the key) and **the cell that changes flashes**. No pre-naming: you *see* what moves, then label
it. Fastest way to find unknown bits.

### B. Guided A-B-A — proof
For a specific named input, walk a scripted toggle and require the bit to track **every**
transition:

```
1. "Make sure DRIVER DOOR is CLOSED.  [Enter]"   -> baseline A
2. "Open the driver door.             [Enter]"   -> active   B
3. "Close it again.                   [Enter]"   -> confirm  A'
   => a bit that went 0->1->0 across A,B,A' is the driver door.
```

A-B-A (or A-B-A-B) is the core idea: a bit that follows every transition is proven; a bit that
changes only once may be coincidence. This mode writes the result to the store.

## The hard part: signal vs noise

This is ~80% of the value. Without it the tool is unusable on a live bus.

1. **Multi-sample per state.** Read the LID set K times (e.g. 5–10) per state; take the **mode**
   per byte. Filters read jitter from the cheap K-line link.
2. **Auto-mask volatile bytes.** Before any toggle, hold a quiet baseline for a few seconds while
   the operator touches nothing. Any byte that changes on its own is a counter / analog value →
   **masked and hidden** from every subsequent diff.
3. **Flag only** bits that are **stable within a state** but **differ between states**, excluding
   masked bytes.
4. **A-B-A confirmation** rejects coincidental one-off changes.

## Architecture (reuse, don't rebuild)

- **`sniff/automap.py` is already the differential mapper** — it consumes
  `EcuSession.read_block(lids) -> {lid_hex: bytes}`. This tool is an **interactive front-end +
  noise mask + A-B-A logic** on top of that shape, not a new mapper.
- **Signal store + `upsert_field`** to write proven bits as `kandidat` (never hand-paste `Signal(...)`).
- **Transport-agnostic**: the same mapper runs over KKL (`SerialTransport`) or the ESP in cable
  mode (`EspTransport`). BCU/airbag need slow init (already on both paths); no new transport work.

### Proposed shape

A `Mapper` that holds the module session and polls a configured LID set at ~1–2 Hz, plus three
primitives the front-ends drive:

- `stable(state) -> {lid: mode_bytes}` — sample K frames, mode per byte, mark volatile bytes.
- `diff(a, b) -> [ (lid, offset, bit, from, to) ]` — bits stable-in-both, differ, minus masked.
- `record(name, bits)` — `upsert_field` into `<module>.json`.

Front-end (web or CLI) only drives the A-B-A flow and the wiggle view over those three.

## Form factor

- **Web on the phone = primary.** In-car the operator is alone, reaching for door handles / the
  key — they want to hold the phone and tap one big button, not reach a laptop keyboard. It also
  fits the existing web UI.
- **CLI (`tools/map_inputs.py`) = bench.** Simplest first cut for bench/desk work.

### Decision to make: who owns the session during mapping?

- **Node "map mode"** — the ESP holds the module session and its web page shows the bit-matrix
  directly. Best one-handed in-car UX, but requires adding slow-init **polling** to the node
  firmware (currently the node only fast-inits TD5 for logging).
- **Cable mode** — Mac/Pi drives it over `EspTransport`; zero new firmware, but needs the computer
  present in the car.

Lean: start with **cable mode + CLI** (no firmware risk), add the **phone-web wiggle view** next,
and only add a node map-mode if one-handed-without-a-laptop turns out to matter.

## Data model / output

Each confirmed bit → `upsert_field` on `<module>.json`:

```
{ lid, offset, kind: "bit", bit_index, name, konfidens: "kandidat",
  note: "differential: <input>, off->on->off, RDL016 <date>" }
```

- Start every mapping as `kandidat`. Promote to `belagt` only after independent re-confirmation in
  a separate session (keep the `belagt`/`kandidat` distinction honest — it propagates to the UI).
- Record the exact toggle procedure + date + reg in the note (ground truth, like the VIN/EKA trick).

## Session / polling notes

- **Light polling** for fragile modules (SLABS-style): few LIDs, ~1 Hz, keepalive — block-reads
  each cycle killed the SLABS session. BCU should be treated the same until proven otherwise.
- **BCU connect quirk**: enters diagnostic mode on an **ignition transition**; needs the right
  key position. Bake the "cycle the ignition" prompt into the connect step.
- **Clean teardown**: end with `endSession`/`release` (StopDiagnosticSession + StopCommunication),
  or the ECU stays stuck (proven on the node — the `20`+`82` fix).

## Safety / guardrails

- **Read-only.** Mapping sends only `21 xx` reads — **never** a `3B` write or any actuator command.
- **Never write to the ECU** during mapping.
- **EKA / PII**: never capture or store the EKA LID (`21 CC`) value; redact it (the code already
  lives in the sister project, and the value is dual-use immobiliser material).

## Phased build plan (when we do it)

1. **Bench CLI** — `Mapper` (stable/diff/record) + A-B-A flow + volatile-byte mask, over cable/KKL,
   writing `kandidat` to `bcu.json`. Prove the de-noising on a known input (driver door).
2. **Phone-web wiggle view** — live bit-matrix that flashes changed cells; tap-to-label.
3. **Node map-mode** (optional) — slow-init polling + bit-matrix served from the ESP, for
   one-handed in-car mapping without a laptop.

## Open questions to settle first

- Session owner: node map-mode vs cable mode (see above).
- Web vs CLI first (lean: CLI bench, then phone-web).
- How to present **multi-bit** inputs (e.g. a 3-position switch spanning several bits).
- Inputs that need the **engine running / ignition on** — how to script those safely.
- Promotion rule `kandidat -> belagt` (how many independent confirmations).
