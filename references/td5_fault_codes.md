# Discovery 2 TD5 (Lucas engine ECU) — fault codes

The engine ECU's fault memory. **Unlike the other modules, TD5 is already
raw-mapped** — we read the faults directly on K-line and decode them bit-by-bit in code.

- **Raw decoder (code):** `src/d2diag/td5/faults.py` — 210 named fault bits
- **Reference (display codes + causes):** the fault-code dictionary (register repo),
  the TD5 section incl. Kelvin's complete forum list (`X-Y` format)
- **Live signals:** `src/d2diag/td5/identifiers.py` (LIDs `21 xx`)

## Raw encoding (PROVEN)
Td5 does **not** read standard DTCs. The fault memory is fetched as a **status block** via
ReadDataByLocalIdentifier `21 3B` (bytes after positive `61 3B`), and cleared via
StartRoutine `0xDD` with 18 zero bytes.

- The block is **35 bytes** (offset 0–34) and **bit-coded**: each bit = one fault.
- **Fault index = offset·8 + bit** (bit 0 = mask `0x01` … bit 7 = `0x80`).
- Set bits without known text are reported generically as `byte<off>.bit<n>` so
  no fault disappears silently.

The map is **proven** from the reference tool Ekaitza_Itzali *and* cross-validated against
**reference tool v1.12** — both give the same name for the same offset/bit (no code copied,
see `THIRD_PARTY_LICENSES.md`).

## Status encoding (offset bands)
The reference tool distinguishes more finely than Ekaitza's coarse Logged/Current. The pattern in the block:

| Offset band | Meaning |
|---|---|
| 0–1 | **Logged Low** — stored, signal low (short circuit/low voltage) |
| 2–3 | **Logged High** — stored, broken circuit (high) |
| 4–5 | **Current** — sensor-circuit faults active right now |
| 6–13 | Driver stage (over-temp / open-load / short), Logged and Current respectively |
| 14–25 | Crankshaft, CAN, boost, driver demand, speed, cruise |
| 26–34 | Injectors 1–6 (peak long/short, open/short/partial) + topside switch |

## Display code ↔ raw (cross-reference still to be sniffed on RDL 016)
The reference tool shows `X-Y` (e.g. `28-7` topside switch). Our raw mapping gives
`offset.bit`. They should be cross-validated by **sniffing the reference tool** while it reads
TD5 faults (capture the raw block + displayed code at the same time) — the same method as for SLABS.
The reference table in the dictionary holds the display codes; this file + `faults.py` hold
the raw encoding.

> 🔴 **`28-7` / `topside switch failed pre-injection`** (offset 27 bit 6, Logged;
> offset 29 bit 6, Current): the forum's strongest clue for *the engine stalling completely /
> the reference tool not getting in* — the topside switch is a solenoid **inside the ECU** that
> fails (especially after moisture). See the dictionary for the whole reasoning. Not seen on
> RDL 016.

## Seen on RDL 016 — raw-sniffed 2026-08-08 (proven)
`21 3B` read during warm idle; our decoder gave: **air flow circuit** (Current +
Logged Low), **inlet air temp** (Logged High), **can tx/rx error** (Logged),
**driver demand** (problem Current + inconsistencies Logged), plus two suspicious ones:
**inj. 6 peak charge long** (Current — but the engine is 5-cyl) and an unknown `byte18.bit6`.
Raw block + full table: see the dictionary, section "Seen on RDL 016 — raw-sniffed".

The same session also proved: SecurityAccess seed `d3 e6` → key `ad 87` (our keygen
is correct), immobiliser status `03` = not immobilised, fast init `0x13`, session `0xA0`.

## New protocols sniffed (beyond faults)
- **Output tests:** IOControl `30 <id> ff` (fuel pump A1, MIL A2, A/C clutch A3,
  A/C fan A4, glow B3, rev-counter B7, temp-gauge BA; wastegate BE / EGR BD with PWM
  parameters). **Injector click:** StartRoutine `31 C2 0<n>` (cyl 1–5).
- **Security:** `31 C0` + `33 C0` → status byte. Implemented in `td5/td5.py`
  (`output_test`, `injector_pulse`, `security_status`); `LEARN SECURITY CODE`
  deliberately not implemented (state-changing).

## reference tool live-data screens → our LIDs (reference 2026-08-19)

External description of the reference tool's Td5 screens, cross-run against our sniffed LIDs.
Confirms mappings and names fields we don't read yet.

| reference tool field | Our LID | Status |
|---|---|---|
| Engine Speed | `21 09` rpm | proven |
| Road Speed | `21 0D` speed | proven |
| Coolant Temp | `21 1A@0` | proven (normal 86–95 °C, thermostat 88, >105 danger) |
| **Turbo Pressure** | `21 1C@0` manifold_press | proven — = boost pressure. Idle ~1.0 bar, full load 2.0–2.2, overboost cut >2.42 |
| Battery Volt | `21 10` | proven (13.8–14.4 V while charging) |
| Ambient Pressure | `21 23` | proven (~1.0 bar sea level) |
| **Air Flow (MAF)** | `21 1C@4` maf_raw | **CANDIDATE — reclassified.** The earlier "no MAF" was wrong; the reference tool shows it. Idle 55–65 kg/hr. Our only reading=0 (engine off). Scale unknown → requires a capture with the engine running |
| Air Inlet Temp | `21 1A@4` air_temp | proven |
| Fuel Temp | `21 1A@12` | proven (~70–80 °C warm, 10–15 below coolant) |
| Cylinder 1–5 balance | `21 40@0..8` | proven (±4 idle; +6…+15 = weak cylinder) |
| Accel Track 1 | `21 1B@0` | proven (0.3→4.7 V) |
| Accel Track 2 | `21 1B@2` | proven (INVERTED 4.7→0.3 V) |
| Accel Track 3 | `21 1B@4` | candidate — **Euro 3 (NNN) only**; 0 on Euro 2 |
| Accel Supply | `21 1B@6` | proven (5.0 V ±0.1) |
| Idle Speed Error | `21 21` rpm_error | proven |

### Still UNMAPPED live fields (reference tool screen 5) — next capture goal
- **EGR Inlet**, **EGR Modulator** (PWM), **Wastegate** (electronically controlled on the D2).
  Probably live in one of the not-yet-interpreted LIDs `0E, 11, 20, 24, 32, 37, 3D`.
  Requires labeled captures (reference tool value + raw bytes) to be mapped.
- **`21 1C@2`**: a second pressure-like u16 (~1.007 bar) next to the manifold — unidentified.
- Switch inputs `21 1E / 21 36 / 21 38` (bitfields) — documented in the handoff, not in the store.

## reference tool SLABS screens → our LIDs

| reference tool field | Our LID | Status |
|---|---|---|
| L/R Height Sensor | `21 54@0/1` | proven (normal ~110–135, calibration-dependent; L≈R on level ground) |
| Wheel speeds FL/FR/RL/RR | `21 43` (4×) | candidate — only FR mapped; raw value ~124 baseline ≠ km/h |
| Door switches | `21 56@0 bit0` any_door | proven — SLABS does NOT adjust the suspension with a door open |
| Valve/target supply V | `21 44@12/13` | candidate — ~12.5–14 V, scale not cross-validated |
| **Shuttle Valve Switches** | `21 42/48/58`? | unmapped — our fault code **027** = classic WABCO circuit-board fault |
| Brake switch, SLS off-road switch | switch LIDs | unmapped (`21 42/48/56/58` bitfields) |
