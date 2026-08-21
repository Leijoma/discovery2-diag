# Td5 Engine ECU (Lucas / Motorola)

The Td5's engine management is a **Lucas (Motorola-based) ECU** on the K-line at
**diagnostic address 0x13**. It is the best-understood module on the car: live
data, fault codes, immobiliser status and output/actuator tests are all working and
verified on the reference car (RDL 016).

Confidence tags follow [the hub legend](../README.md): 🟢 Proven (verified on the
car), 🟡 Assumed (derived/matched, unverified), 🔴 Unknown (open).

## Connection & security

| Step | Bytes | Confidence | Evidence |
|---|---|---|---|
| Fast init (StartCommunication) | addressed `81 13 F7 81 …`, expect `C1` | 🟢 | Connects reliably after the init-pulse fix; see [kline-protocol.md](kline-protocol.md) |
| StartDiagnosticSession | `10 A0` | 🟢 | Td5 diagnostic session 0xA0 |
| SecurityAccess — request seed | `27 01` → `67 01 <seed_hi> <seed_lo>` | 🟢 | |
| SecurityAccess — send key | `27 02 <key_hi> <key_lo>` → `67 02` | 🟢 | Key = LFSR seed→key (taps at bits 1,2,8,9), ported from `td5keygen` (BSD-2) |

After the key is accepted the ECU is unlocked and `21 xx` reads work. The whole
sequence is wrapped in a tolerant retry (`EcuSession._establish`).

### Immobiliser / security status 🟢

Read-only status of the immobiliser handshake, equivalent to the factory tool's
"GET SECURITY STATUS":

| Action | Bytes | Meaning |
|---|---|---|
| Start routine | `31 C0` | start the security-status routine |
| Read result | `33 C0` → `… <status>` | **status byte `0x03` = not immobilised** |

Proven on RDL 016 (status = 0x03). We deliberately do **not** implement "learn
security code" — that is a state-changing routine and out of scope for a read-only
tool.

## Live parameters (ReadDataByLocalIdentifier `21 xx`)

Offsets are into the data field returned after the echoed identifier. Scale/bias:
`value = raw × scale + bias`. Temperatures are Kelvin×10 (`raw × 0.1 − 273.2`).

| Signal | LID@offset | type × scale | Unit | Confidence | Normal range |
|---|---|---|---|---|---|
| rpm | 21 09@0 | u16 ×1.0 | rpm | 🟢 | 0–4800 |
| speed | 21 0D@0 | u8 ×1.0 | km/h | 🟢 | 0–200 |
| battery | 21 10@0 | u16 ×0.001 | V | 🟢 | 11.5–15.5 |
| coolant_temp | 21 1A@0 | u16 ×0.1 −273.2 | °C | 🟢 | −40–105 |
| air_temp (IAT) | 21 1A@4 | u16 ×0.1 −273.2 | °C | 🟢 | −30–80 |
| ext_temp | 21 1A@8 | u16 ×0.1 −273.2 | °C | 🟡 | see note ⚠️ |
| fuel_temp | 21 1A@12 | u16 ×0.1 −273.2 | °C | 🟢 | −30–90 |
| accel_way1 | 21 1B@0 | u16 ×0.001 | V | 🟢 | 0–5.1 |
| accel_way2 | 21 1B@2 | u16 ×0.001 | V | 🟢 | 0–5.1 |
| accel_way3 | 21 1B@4 | u16 ×0.001 | V | 🟢 | 0–5.1 (Euro 3 only) |
| accel_supply | 21 1B@6 | u16 ×0.001 | V | 🟢 | 4.9–5.1 |
| manifold_press (MAP/boost) | 21 1C@0 | u16 ×0.0001 | bar | 🟢 | 0.8–2.6 |
| maf_raw | 21 1C@4 | u16 ×1.0 | — | 🟡 | status field, **not** airflow |
| **maf (mass air flow)** | **21 1D@5** | **u8 ×1.0** | **kg/hr** | 🟢 | **55–65 idle → 185–200 @2000** |
| injection_qty | 21 1D@6 | u16 ×0.01 | mg/stroke | 🟡 | ~12 idle, ~23 load, ~3.6 overrun (fuel cut) |
| rpm_error | 21 21@0 | s16 ×1.0 | rpm | 🟢 | −300–300 (idle only) |
| ambient_press_1 | 21 23@0 | u16 ×0.0001 | bar | 🟢 | 0.8–1.1 |
| ambient_press_2 | 21 23@2 | u16 ×0.0001 | bar | 🟢 | 0.8–1.1 |
| balance_1…5 (cylinder) | 21 40@0,2,4,6,8 | s16 ×1.0 | — | 🟢 | −12–12 |

### MAF — how it was found, and why it's Proven 🟢

The real mass-air-flow reading is **a single byte** at `21 1D` byte 5, in **kg/hr
directly**. Found 2026-08-21 by logging a rev sweep and binning every byte against
rpm: `1D` byte 5 read **69 at idle → 184 at ~2000 rpm** (2.7×), matching the
published Td5 reference tool ranges (idle 55–65, 2000 rpm 185–200, high load 3000 rpm
550–600, overboost cut ~618–650). The sensor on RDL 016 is **healthy** (12 V feed
on pin 3, pin1–2 = 17 kΩ, live signal tracks load). Ekaitza_Itzali's sniff logs
independently label the `21 1D` block "fuel-usage params", corroborating the block.

> ⚠️ Attribution: the scale (raw = kg/hr) is matched to *published forum ranges*,
> not a reference tool reading on RDL 016 itself. Identification is strong; the scale may
> want fine-tuning against a live factory-tool value.

`maf_raw` (`1C@4`) is **not** airflow — it reads a constant ~48 key-on and 0 while
running (the opposite of MAF); it is an unidentified status/mode field.

### ⚠️ ext_temp is a phantom 🟡→ghost

`21 1A@8` decodes to a constant **150.0 °C** (`raw = 0x1088`). There is **no
external-temperature sensor on the Td5 ECU** — real ambient (~17 °C, confirmed in
the car 2026-08-21) is measured by the instrument cluster via the BCU, not the
engine ECU. The 150 °C is meaningless; the tool flags it as *suspect* (limits
−40…50) so it shows struck-through rather than as a real temperature. In Td5 terms
"ambient temperature" = the airbox/intake air = **air_temp (IAT)**, and "ambient
pressure" = **ambient_press** (barometric).

## Outputs / actuator tests (InputOutputControl `0x30`) 🟢

Frame `30 <LID> <state…>`, positive response `0x70`. **Run stationary, ignition on,
engine off, behind explicit confirmation** — these energise real hardware.

| Output | Bytes |
|---|---|
| Fuel pump | `30 A1 FF` |
| MIL lamp | `30 A2 FF` |
| A/C clutch | `30 A3 FF` |
| A/C fan | `30 A4 FF` |
| Glow plugs | `30 B3 FF` |
| Rev-counter sweep | `30 B7 FF` |
| Temp-gauge sweep | `30 BA FF` |
| EGR modulator (PWM) | `30 BD FF 00 FA 13 88` |
| Wastegate modulator (PWM) | `30 BE FF 00 0A 13 88` | 🟡 (from Ekaitza captures; not yet run from our code) |

**Injector cut / balance test** (StartRoutine `0x31`): `31 C2 01` … `31 C2 05` for
cylinders 1–5, response `0x71`. 🟢 (implemented as `injector_pulse`).

## Fault codes

Read with `21 3B` — **210 raw-mapped bits**, indexed `byte×8 + bit`. Clear with
StartRoutine `0xDD` + 18×`00` (expect a delayed ~300 ms `54` ack). See
[fault-codes.md](fault-codes.md) for the table and the RDL 016 baseline (the real
faults were `001-07` EGR vacuum module and `004-01` inlet-air-temp circuit).

## Full-coverage polling

To avoid missing fields like MAF again, the tool raw-logs **every LID the factory
tool polls**, including unmapped ones. Beyond the mapped set it reads `1E, 1F, 20`
(confirmed responders) and candidate `37, 38` (EGR / wastegate position, from
SimonRafferty — 🟡 unverified) every cycle, so any unknown field can be found from
an ordinary drive log with `tools/raw_analyze.py`.

## Open questions 🔴

| Item | What we know | Needed |
|---|---|---|
| Injection quantity **(candidate found 🟡)** | `21 1D@6` u16 ÷100 → mg/stroke — fuel-cut-on-overrun signature confirmed on a loaded drive (2026-08-21). Drives a live **fuel computer**: fuel_rate (L/h), momentary/trip/lifetime economy (L/100 km); validated ~8 L/100 km. | One clean overrun drive or a factory-tool cross-read to promote the scale to 🟢. |
| ~~EGR / wastegate position 37/38~~ **(resolved 🔴)** | `21 37 / 21 38` do **not** respond on RDL 016 — SimonRafferty's LIDs don't apply here. `21 20` is a constant too (not injection, contra SimonRafferty). | — |
| Digital inputs / switches | `21 1E` (and `21 36`) are bitfields: brake, clutch, cruise, A/C. Ekaitza gives a pin map. | Decode the bitfield against physical switch states. |
| VIN / ECU identity | `1A 87` VIN, `1A 9A` ECU type (from Ekaitza). | Add the read; confirm the format. |
| Other `1D` / `1E` / `1F` / `20` bytes | Respond and some move with rpm. | Map against known values. |
| `maf_raw` (1C@4) meaning | Constant ~48 off / 0 running. | Identify what this status field actually is. |
