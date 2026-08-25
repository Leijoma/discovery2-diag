# Td5 — findings from external repos (research 2026-08-21)

Review of EA2EGA/Ekaitza_Itzali (Python, real sniff logs), SimonRafferty
and muki01. Purpose: find what we do NOT already have. We turned out to be in good shape.

## Already implemented on our side (confirmed by Ekaitza's real sniffs)
- **Immobiliser/security status** — `security_status()` = `31 C0` + `33 C0`,
  RDL016 = **0x03 (not immobilised), proven**. NOTE: Ekaitza's README lists this
  as "Not yet" (unimplemented) — WE have it independently. "Learn code" is deliberately NOT done.
  ⚠️ Not yet shown in the v2 UI ("security status: planned").
- **Outputs `0x30`** — our `_OUTPUTS` matches Ekaitza's captured bytes exactly:
  A1 fuel pump · A2 MIL · A3 A/C clutch · A4 A/C fan · B3 glow plugs · B7 rev-counter
  sweep · BA temp-gauge sweep · BD EGR modulator (PWM).
- **Injector tests** `31 C2 01…05` (cylinder balance) — has `injector_pulse`.
- **Seed→key** LFSR (taps bits 1,2,8,9) — has a keygen.
- **Checksum = sum(all bytes incl. length) mod 256** — confirms the `raw_analyze` parser.
- **Fast init 25 ms low + 25 ms high** — matches ours (muki01 in
  `references/muki01_OBD2_K-line_Reader/`, Wayback capture, MIT).

## New to possibly adopt (unverified against RDL016 — confirm first)
- **`21 1D` = "fuel-usage params"** (Ekaitza) → confirms that MAF (1D@5) AND
  fuel/injection data live in the 1D block. **The route to fuel consumption** goes via
  injection quantity (mg/stroke) in 1D — hunt the field from a LOADED drive (byte1 27→65,
  byte11 50→127 moved with rpm; load distinguishes injection from pure rpm fields).
  - **1D fuelling-block decode (2026-08-22, candidate).** From the night drive + the
    Nanocom fuelling-page field ORDER (Ambient, Manifold, EGR Modulator, EGR Inlet,
    Wastegate): **1D@15 = EGR modulator %** and **1D@17 = wastegate modulator %** (`u8 ×
    100/255`), plus **1D@4 = a 2nd MAP reading** (r=0.995 vs manifold). Confirmed across
    FOUR drives 2026-08-21/22: @15 high-light-load→0-load (textbook EGR); @17 follows boost
    (r=0.85) but is not MAP, scaled ~6%→32% = the published band (0 idle / 20-40 boost).
    **`1D@16` is a constant-0 dead/reserved byte across all four drives** — NOT EGR inlet (a
    first mis-map by page order; removed). **EGR Inlet % not yet located** (1D@14 varies but
    unidentified). Scaling 100/255 not cross-checked vs a factory tool. In the store as
    `kandidat`.
  - **Injector classification codes** (Injector 1-5, five-char each, a Settings-block read):
    the dashboard never polls the identifier/Settings blocks, so these are in NO raw log —
    needs a targeted read on the car.
- **ECU identification `1A xx`**: `1A 87` VIN · `1A 9A` ECU type · `1A 9B/9C` more IDs.
  (Read-only, easy to add — we don't read VIN today.)
- **Digital inputs / switches `21 1E` and `21 36`** (bitfields): brake, clutch,
  cruise, A/C request, transfer position. Ekaitza gives pin mapping (A33 transfer, B10/B16
  brake, B35 clutch, B15/B17/B11 cruise, B9/B23 A/C). We capture 1E in the raw log but
  **don't decode the bitfield** — a concrete mapping task.
- **`21 32` / `21 0E`** homologation/map variant (ASCII) · **`21 3D`** 14-byte status block.
- **`30 BE` wastegate modulator** (we have BD EGR but possibly not BE wastegate — check).

## Low reuse
- colinbourassa/libcomm14cux (Rover V8 14CUX) + memsgauge (MEMS 1.6): NOT KWP2000,
  only a K-line/FTDI wiring reference.
- Zi-x/OBD-KLINE: generic ISO14230, nothing Td5-specific.

## Attribution
Ekaitza's sniff logs = high trust (captured from a real Td5). SimonRafferty reads as
partly reconstructed and clashes with our car-verified LID scheme (MAF@1B etc.) →
lower trust; verify its `21 37/38` (EGR/wastegate position) against the car first.

---

# BinOwl_Td5Gauge — review 2026-08-25

`k0sci3j/BinOwl_Td5Gauge` (GPL-3.0, 2022): an ESP32 Td5 gauge with LCD + WiFi web
readout. Read as a **protocol reference only — no code taken** (GPL-3.0 is
incompatible with this repo; see THIRD_PARTY_LICENSES.md). The whole K-line layer
is `main/KLine.cpp`, ~300 lines, with the LID→field mapping in plain sight.

## Confirms what we already had (independent second source)
- Init `81 13 F7 81` → `10 A0` → `27 01`/`27 02`, keepalive `3E 01`, checksum =
  sum of all bytes. Fast init 25 ms low / 25 ms high (their code adds 500 µs to each).
- **Keygen is bit-identical to ours**, including the iteration count
  `((q>>0xC&8)|(q>>5&4)|(q>>3&2)|(q&1))+1` and the taps 1/2/8/9 — a third
  independent confirmation of `td5/keygen.py`.
- `09`=rpm, `0D`=speed u8, `1A`@0/@4/@12 = coolant/air/fuel temp (u16/10−273),
  `1B` = 3 pedal tracks + supply (u16/1000 V), `1C`@0 = MAP, `23`@0/@2 = ambient
  ×2, `40` = 5×s16 cylinder balance, `1D`@6 = injected quantity (they call it
  `fuel_injected`, ×0.01 — **same offset and same scale as our `injection_qty`**).
- Pressure unit: they print `1C`@0 and `23` as `/100 kPa` = our `/10000 bar`. Same thing.

## New — worth testing on the car
- **`21 1C` is an 8-byte block.** We map @0 (MAP) and used to carry @4 as the raw
  `maf_raw` candidate; BinOwl names and scales the rest: @2 = "MAP raw" (u16/100 kPa)
  and **@4 = MAF, u16/10 kg/h**. Frame length checks out against our own capture
  `0a 61 1c 27 5e 27 74 00 00 00 9c`
  (`references/captures/td5_slabs_session_20260808.log`) = MAP 1.0078 bar, MAP-raw
  1.0100 bar, @4 = 0x0000, @6 = 0x009C (constant 156, unmapped).
- **`21 38` = turbo wastegate modulator, u16/1000 %.** We never read `38`. Our
  8/8 capture has `04 61 38 00 00` and `04 61 37 00 00` at idle = 0.0 %, which is
  what a wastegate duty should read at idle. SimonRafferty independently claims
  `37`/`38` are EGR/wastegate — two unrelated sources now agree on `38`.
- **`21 1D`@0 = driver's fuel demand** and **`21 1D`@14 = idle fuel demand**
  (both u16 ×0.01, same scale as the injected quantity at @6). @14 was listed as
  "varies but unidentified" above — this names it.
- **`21 1B` has two frame lengths** in their code: 12 bytes total with supply@6
  ("MSB") vs 14 bytes with supply@8 ("NNN"), auto-detected at runtime. RDL 016
  returns the **12-byte** form (`0a 61 1b …`, supply@6 = 5.010 V), so our mapping is
  right for this car — but a portable reader must sniff the length, not assume @6.
  (Note this cuts against the "way3 active ⇒ NNN" reading in the signal store;
  their length heuristic and our variant label disagree. Harmless for us, unclear in general.)

## The MAF question — this is the interesting part
This is not a new offset for us: `1C`@4 was in the signal store as `maf_raw`
(`kandidat`, unscaled) until commit `bba77a9` remapped `maf` to `1D`@4 u16 with a
provisional 2-point calibration, justified by r=+0.95 vs rpm×MAP over a WOT pull.
What BinOwl adds is the **name and scale** for `1C`@4 (MAF, u16/10 kg/h) — i.e. an
independent claim that this is where a *working* Td5 reports measured air mass.

Checked against our own logs (2026-08-25, offline):

| Log | n | `1C`@4 zeros | max | r vs rpm×MAP |
| --- | --- | --- | --- | --- |
| `livedata-20260821-080743.csv` | 113 | 109 | 60 | −0.32 |
| `livedata-20260821-082745.csv` | 503 | 502 | 51080 | +0.30 |
| `livedata-20260820-095417.csv` | 131 | 121 | 57 | −0.09 |

So `1C`@4 is a **flat-zero channel with occasional junk blips** (the single 51080 is
almost certainly a corrupt read — cf. the comms-glitch vs sensor-fault split in
`TODO.md`), across idle, load and >2500 rpm alike. The 2026-08-08 capture agrees.

That is not evidence against BinOwl's mapping. RDL 016 has **`air flow circuit
(Current)`** as a live fault in every recent log (plus `inlet air temp. circuit`, the
IAT that sits in the same MAF housing). A MAF circuit that reads exactly zero with
sporadic garbage is precisely the expected symptom — and the old menu entry for this
field already carried the note "no MAF sensor".

If that holds, `1C`@4 is the **measured** MAF (zero here, sensor faulted) and our
`1D`@4 is a **modelled/speed-density** air mass — which explains both the r=0.95
against rpm×MAP and why the 2-point calibration never felt solid. Both can be true at
once, and the dashboard is currently showing a modelled value under a measured name.

**Test:** `references/test_plan.md` T-01 (read the full `21 1C` block on a Td5 with a
healthy MAF, or on RDL 016 once the air-flow fault is fixed) and T-02 (`21 38` vs
`1D`@17 over a boost pull).

## Do NOT copy
Their L/h formula is `mg/stroke × rpm × 2.5 × 60 / 1e6 × 0.83`. The density
belongs in the denominator (kg/h → L/h is ÷0.832), so theirs reads ~45 % low.
`web/sources.py::_FuelComputer` already divides. Their `21 10` voltage decode
(`data[3] | data[2]<<8 | data[4]`) is also visibly wrong; ours (`10`@0 u16/1000) is
verified against the car.
