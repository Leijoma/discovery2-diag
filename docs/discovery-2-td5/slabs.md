# SLABS — Wabco ABS + rear self-levelling suspension

The **SLABS** ECU is the Wabco unit that runs both the **anti-lock brakes (ABS,
plus traction control and hill-descent control)** *and* the **rear
self-levelling suspension (SLS)** of a Land Rover Discovery 2. On the D2 these
two functions live in **one** ECU on the K-line — that is what "SLABS" (Self
Levelling And aBS) means.

> ⚠️ This is **not** the Range Rover P38 arrangement. The P38 splits the job into
> a separate ABS ECU and a separate EAS (air-suspension) ECU. On the D2 it is a
> single Wabco box, and *every* D2 has one — there is no non-ABS / non-SLS
> variant to worry about.

All facts below are tagged with the project
[confidence legend](../README.md#confidence-legend): 🟢 **Proven** (sent on the
real car, reg. RDL 016, and confirmed), 🟡 **Assumed** (derived/transcribed, not
yet confirmed), 🔴 **Unknown** (visible but not yet interpreted). The evidence and
date are cited for each claim. The single source of truth for the signal tags is
`src/d2diag/signals/slabs.json`; this page reflects it, it does not override it.

## Connection at a glance

| Property | Value | Confidence |
|---|---|---|
| Address | `0x29` | 🟢 Proven — sniffed factory-tool traffic 2026-08-07, live init since 2026-08-19 |
| Init | **Fast init**, `81 29 F7 81 22` → `C1 57 8F` (KWP2000, KW2 = `8F`) | 🟢 Proven |
| Diagnostic session | **None** — no `StartDiagnosticSession` | 🟢 Proven (services work right after fast init) |
| Security access | **None** — no seed/key unlock | 🟢 Proven |
| Session framing | Unaddressed, length-prefixed `<len> <SID> … <cs>` (checksum = byte-sum & 0xFF) | 🟢 Proven |
| Keepalive | **bare `3E`** (`01 3E` → `7E`), ~1 Hz | 🟢 Proven |
| Ignition | Ignition **ON** required; comms die above ~8–20 km/h → work stationary | 🟢 Proven |

Unlike the Td5 engine ECU, SLABS needs neither a diagnostic session nor a
SecurityAccess unlock: after fast init you go straight to the services. In the
code this is expressed by `Slabs.establish()` calling the shared
`EcuSession._establish(after=None)` (Td5 passes `after=self.connect`).

### Keepalive is a *bare* `3E` — `3E 01` kills the session

SLABS wants `TesterPresent` as a bare `3E` (sniffed frame `01 3e 3f`). Sending
`3E 01` (the sub-function form the Td5 uses) gets **no answer and tears the
session down**. In code this is `Slabs._keepalive_sub = None`. 🟢 Proven
(`references/slabs_protocol.md`).

### Establishing the link on a shared bus

The K-line is a single shared wire. Two hard-won rules apply (both 🟢 Proven in
the car, 2026-08-18):

- **`7F 81 10` (generalReject) on StartCommunication means a link is still open**
  — often left by another module or a previous process that died with its link
  up. `EcuSession.release()` ends a module with `20` (StopDiagnosticSession, Td5
  only) **and always** `82` (StopCommunication, every module), and `_establish`
  sends a best-effort `82` before *every* init attempt. Always end a module with
  `release()`, never a bare `close()`.
- **Init needs a *quiet period*, not more attempts.** Every successful factory-
  tool init in the sniffs landed on the *first* try after ~25–52 s of silence
  toward the module; hammering it resets that wait and is actively harmful (it is
  what locked us out for ~2 min on 2026-08-18). The driver uses `idle=0.3 s`,
  `attempts=3`, `retry_sleep=28 s`.
- The real fix that made init reliable was the **fast-init pulse timing**: our
  TiniH was ~32 ms instead of the ISO 25 ms. After correcting it (spin-wait
  instead of `sleep`, counting the UART stop bit) the per-attempt hit rate went
  from ~9 % to ~55 % and the dashboard connects on the first attempt (2026-08-19,
  Fisher's exact p = 0.007). 🟢 Proven.
- After `C1`, the driver mirrors the factory tool by sending `1A 8A`
  (`ReadEcuIdentification`) ~170 ms later and using the reply as a **confirmation
  that the session is really alive** — the tolerant init only searches the read
  burst for a `C1` and can be fooled by the half-duplex echo of our own frame on
  a quiet bus. A failed confirmation is reported via `progress`, not treated as
  fatal.

> 🟡 Open work note: address mode (physical `0xF7` vs functional `0xF1`) and
> engine-running-vs-off were both investigated as connection-reliability factors.
> With shuffled attempt order the address-mode difference **vanished** — it was a
> position effect, not a real effect (2026-08-19). "Run the engine while talking
> to SLABS" is the strongest correlation measured but is **not** established
> (n=8, p=0.27); treat it as a working rule, not a proven cause.

## ⚠️ CRITICAL: SLABS must be polled *lightly*

This is the single most important operational rule for this module.

**Block-reading many LIDs on every cycle kills the session after ~15 s.** An
early store-driven block read of 5 LIDs + fault codes on *every* 0.5 s cycle
(~7× the reference bus traffic) connected fine but died after ~15 s. 🟢 Proven
2026-08-07.

**The rate matters as much as the number of LIDs.** Even reading only `21 54`
each cycle was too much at the server's 0.5 s tick (`3E` + `21 54` = 4 frames/s),
versus the factory tool's ~1 Hz. The session died after 21 s (connected 20:54:28,
dead 20:54:49). 🟢 Proven in the car 2026-08-18.

The tool therefore throttles on **the clock, not the poll cycle**
(`src/d2diag/web/sources.py`):

| Constant | Value | Meaning |
|---|---|---|
| `_SLABS_BUS_PERIOD` | `1.0 s` | Minimum wall-clock time between bus touches; extra polls return cached values without touching the bus |
| `_SLABS_FAULT_PERIOD` | `30.0 s` | Fault codes read on their own slow cadence (2 extra frames) |
| `_SLABS_EMPTY_GRACE` | `3` | Empty polls tolerated (showing last-known "stale" values) before forcing a ~20 s reconnect |

Per bus cycle `SlabsDataSource.poll()` sends only:

1. a keepalive `3E` (best-effort — a dropped `3E` does not tear the session),
2. **heights (`21 54`) every cycle**,
3. **exactly one** rotating LID from the reference tool coverage set.

That is `3E` + 2 reads ≈ 1 Hz. Once connected, SLABS then sits **stable** — it
held 2 min 25 s with no reconnect once the light poll was in place (2026-08-18,
🟢 Proven). Do **not** run a fast module-switching fault-watch against SLABS.

## Live parameters

Everything the tool actually decodes today, straight from
`src/d2diag/signals/slabs.json`. Values are raw unless a scale is shown.
`u16le` = little-endian 16-bit.

| Name | LID / offset | Type · scale | Unit | Confidence | Evidence |
|---|---|---|---|---|---|
| `height_left` | `21 54` @0 | u8 | — | 🟢 Proven | `21 54` byte0 = left height; confirmed via variance vs reference tool reference, session.log 2026-08-08. Normal ~110–135 (calibration-dependent); L and R should sit close on level ground; a stuck 0/255 = broken arm/sensor. |
| `height_right` | `21 54` @1 | u8 | — | 🟢 Proven | `21 54` byte1 = right height; same evidence as left. |
| `height_left_mm` | derived | `height_left × 1.4` | mm | 🟢 Proven (derived) | UI-only convenience field (SVG car), derived from the proven left height; not stored in `slabs.json` (`sources.py`). |
| `height_right_mm` | derived | `height_right × 1.4` | mm | 🟢 Proven (derived) | As above, from the proven right height. |
| `any_door` | `21 56` @0 bit 0 | bit (0 = closed, 1 = open) | — | 🟢 Proven | `21 56` byte0 bit0 = any-door; confirmed via differential 2026-08-08 (`00` closed / `01` open). |
| `battery` | `21 44` @12 | u8 × 0.0625 | V | 🟢 Proven | `21 44` byte12. Confirmed in the car 2026-08-20: 13.5 V engine running (charging), 12.0 V engine off — tracks system voltage correctly. |
| `ecu_supply` | `21 44` @13 | u8 × 0.0625 | V | 🟢 Proven | `21 44` byte13. Confirmed 2026-08-20: same as battery (13.5 V engine on, 12.0 V off). |
| `wheel_speed_fl` | `21 43` @0 | u16le | — | 🟡 Assumed | `21 43`@0. Decoding confirmed in car 2026-08-20 (all four read 124 stationary, ≠ km/h). ⚠ **Wheel order** (which offset = which wheel) unconfirmed — all equally still, can't be told apart; needs a spin-one-wheel test. |
| `wheel_speed_fr` | `21 43` @2 | u16le | — | 🟡 Assumed | `21 43`@2. As above. |
| `wheel_speed_rl` | `21 43` @4 | u16le | — | 🟡 Assumed | `21 43`@4. As above. |
| `wheel_speed_rr` | `21 43` @6 | u16le | — | 🟡 Assumed | `21 43`@6. As above. |
| `abs_sensor_fl` | `21 50` @0 | u8 × 0.02 | V | 🟡 Assumed | `21 50`@0. Decoding confirmed 2026-08-20 (all ~2.3 V steady). ⚠ Wheel order unconfirmed. |
| `abs_sensor_fr` | `21 50` @1 | u8 × 0.02 | V | 🟡 Assumed | `21 50`@1. As above. |
| `abs_sensor_rl` | `21 50` @2 | u8 × 0.02 | V | 🟡 Assumed | `21 50`@2. As above. |
| `abs_sensor_rr` | `21 50` @3 | u8 × 0.02 | V | 🟡 Assumed | `21 50`@3. As above. |

### Wheel-order caveat (🟡)

For the four wheel-speeds (`21 43`) and four ABS sensor voltages (`21 50`), the
**scale/decoding is proven** but the **wheel-to-offset mapping is not**. Standing
still, all four channels read the same value, so there is nothing to tell them
apart. The assumed order follows the factory-tool screen order **FR/FL/RR/RL**
and the modulator bit-mask order (see [Actuators](#actuators-startroutine-31-xx)),
but confirming it needs a spin-one-wheel test. Until then these stay 🟡 Assumed.

## Full reference tool / factory-tool input LID set

The factory tool polls a fixed set of input LIDs per screen. All of them are now
*identified* (which screen they belong to); most are **not yet decoded** to
offset/scale. The tool rotates the whole set — `_SLABS_COVERAGE` in
`sources.py` = `{0x11, 0x3B, 0x42–0x59}` — **one LID per cycle** so the poll stays
light; unmapped LIDs are still captured to the raw log for future mapping.

| LID | Screen / believed content | Confidence |
|---|---|---|
| `21 11` | **Logged faults** — 16-byte bit-per-fault block | 🟢 Proven |
| `21 3B` | Polled by the tool; content not yet isolated | 🔴 Unknown |
| `21 42` | Switch block (Neutral / Diff / HDC / Shuttle …) | 🟡 Assumed |
| `21 43` | **4× wheel speed** (2 bytes/wheel) — decoded, wheel order 🟡 | 🟡 Assumed |
| `21 44` | Rich analog block (14 B): 8 valve voltages + pump relay/monitor + **battery @12** + **ECU supply @13** | 🟢 Proven (batt/supply) / 🔴 (valves) |
| `21 45` | Setting — stable raw `7f` (RDL 016); which setting is unsolved | 🟡 Assumed |
| `21 46` | Setting — stable raw `78 76`; which setting unsolved | 🟡 Assumed |
| `21 47` | **Current faults** — 16-byte bit-per-fault block | 🟢 Proven |
| `21 48` | Switch block (`94 61`) | 🟡 Assumed |
| `21 49` | Setting / CAN-derived — stable `00 00 01` | 🟡 Assumed |
| `21 50` | **4× ABS sensor voltage** (1 byte/wheel) — decoded, wheel order 🟡 | 🟡 Assumed |
| `21 53` | SLS L/R sensor supply / value (V) — byte0 varies (~`0xd2`) | 🟡 Assumed |
| `21 54` | **L/R height** (byte0 = left, byte1 = right) | 🟢 Proven |
| `21 55` | SLS compressor relay (V)? — byte3 varies | 🟡 Assumed |
| `21 56` | Switch block; **byte0 bit0 = any-door** (proven), other bits 🔴 | 🟢/🔴 |
| `21 57` | CAN-derived (engine speed/torque/throttle)? — byte0 varies | 🟡 Assumed |
| `21 58` | Switch block (`32 …`) | 🟡 Assumed |
| `21 59` | Setting — stable `00 0f 0f 0f` | 🟡 Assumed |

**Settings caveat (🟡):** the four settings LIDs (`45`, `46`, `49`, `59`) have
stable raw bytes on RDL 016, but *which LID = which setting* (test status /
transport mode / ECU calibrated / suspension type AIR-vs-springs) is **unsolved** —
two order-based labellings from 2026-08-08 and -09 contradict each other. The fix
is a differential: toggle **one** setting in the factory tool and watch which raw
byte moves.

## Fault codes

Fault memory is read as a **16-byte bit-per-fault block** (same technique as the
Td5's `21 3B`) via two identifiers, and cleared with one service:

| Operation | Command | Response | Confidence |
|---|---|---|---|
| Logged faults | `21 11` | 16-byte block | 🟢 Proven |
| Current faults | `21 47` | 16-byte block | 🟢 Proven |
| Clear faults | `14 FF FF` | `54` | 🟢 Proven |

A set bit at `(byte-offset, bit)` = one fault. `clear_faults()` uses a wider read
window (gap 0.5 s, overall 2.5 s) because SLABS writes EEPROM and only ACKs `54`
~300 ms later — the standard 60 ms window returned just the echo and looked like
"empty response" although the clear had succeeded. 🟢 Proven (session.log).

### Confirmed bit → fault anchors

Only two `(byte, bit) → number` anchors are confirmed, from the 2026-08-07 sniff
where `21 11` = `00 00 00 10 … 00 10 …` (bits at byte3.bit4 and byte10.bit4)
matched the car's two known baseline faults (`SLABS_FAULT_BITS` in
`src/d2diag/slabs/faults.py`):

| byte, bit | Number | Text | Confidence |
|---|---|---|---|
| (3, 4) | `020` | front right wheel-speed sensor — output too low | 🟢 Proven (anchor) |
| (10, 4) | `027` | shuttle valve switch — electrical failure | 🟢 Proven (anchor) |

Every other set bit decodes generically as `"unknown (byte i, bit b)"` until more
anchors are captured (via the "provoke a known fault" technique).

### ⚠️ Raw-index ↔ display-number mismatch

**The numbers `020`/`027` above are the factory tool's *display* numbers from the
sniffed session, matched to the two faults known to be on the car** — they are
**not** guaranteed to be the same as the numbers in a published fault list. The
number→text list in `references/slabs_fault_codes.md` (sourced from
rswsolutions.com, faults `012`–`114`) is a **display-number** table and even
disagrees on those two numbers (its `020` = "No Batt Supply Voltage", its `044`/
`046` = front-right/-left sensor "output low"). So the raw 16-byte bit positions,
the tool's display numbers, and any published list are **three separate
numbering spaces** that must be cross-validated bit-by-bit — do not assume a bit
index equals a display number. This mirrors the same caveat on the Td5 side.

## Actuators / StartRoutine (`31 xx`)

> ⚠️ **These touch hardware. Stationary, ignition on, at your own risk.** The
> bleed routines drive the brake system.

All routines answer `71 <rid> 20`. Commands below are 🟢 Proven from the
2026-08-07 sniff (the exact bytes were observed on the bus). Where noted "first
run from our code", the bytes are proven-from-sniff but our tool driving them has
not yet been round-tripped on the car.

| Routine | Command | Confidence |
|---|---|---|
| SLS exhaust valve | `31 2F 28` | 🟢 Proven (sniffed) |
| SLS compressor | `31 30 28` | 🟢 Proven |
| SLS buzzer | `31 31 0a` | 🟢 Proven (audible — good write-verification) |
| ABS pump relay | `31 25 08 fa` (on) / `31 25 02 fa` (off) | 🟢 Proven (on/off preliminary; trailing byte is checksum) |
| Raise left / right | `31 33 28` / `31 34 28` | 🟢 Proven |
| Lower left / right | `31 35 28` / `31 36 28` | 🟢 Proven |
| Per-wheel ABS valve test | `31 22 <sub> <mask> c1 f4` + 8×`00` | 🟢 Proven |

**Per-wheel valve test bit-mask** (`31 22`): `sub` = `0x10 + wheel index`, `mask` =
2 bits per wheel in order **FR, FL, RR, RL** — `03` = FR (bits 0–1), `0c` = FL
(2–3), `30` = RR (4–5), `c0` = RL (6–7); the two bits are in/out valve. `c1 f4`
constant (likely duration/timeout). In code: `Slabs._WHEEL` /
`Slabs.wheel_test(corner)`, corner ∈ {`fl`, `fr`, `rl`, `rr`}.

### ABS bleed routines

Two procedures under `RID_ABS_TEST` (`31 22`), distinct from the per-wheel valve
test. The **command frames are proven from the 2026-08-07 sniff**; our code
issues them as `Slabs.abs_power_bleed()` / `abs_module_bleed_step()` /
`abs_module_bleed()`, and the **first run from our own code** against the car has
not been logged yet — so treat the *frames* as 🟢 Proven and *our driving of
them* as 🟡 to be confirmed on the next car session.

| Routine | Data after `31 22` | Method |
|---|---|---|
| Power bleed — **start** | `04 00 49 c4` + 8×`00` | `abs_power_bleed(True)` |
| Power bleed — **stop** | `04 00 40 00` + 8×`00` | `abs_power_bleed(False)` |
| Module bleed step 1 | `11 00 c0 7d 00 bb` + 6×`00` | `abs_module_bleed_step(1)` |
| Module bleed step 2 | `12 00 c0 7d 00 bb` + 6×`00` | `abs_module_bleed_step(2)` |
| Module bleed step 3 | `13 00 c0 7d 00 bb` + 6×`00` | `abs_module_bleed_step(3)` |
| Module bleed step 4 | `14 00 c0 7d 00 bb` + 6×`00` | `abs_module_bleed_step(4)` |

- **Power bleed** runs the ABS pump to push fluid through the modulator.
- **Module bleed** cycles modulator circuits `0x11`→`0x14` in sequence.
  `abs_module_bleed()` runs all four steps with ~2.3 s between them (the factory
  tool's cadence). All answer `71 22 20`.

The web layer exposes these as actuator actions `bleed_power_on`,
`bleed_power_off`, `bleed_module` (`_SLABS_ACTUATORS` / `_slabs_do` in
`sources.py`).

## ECU identification (`1A xx`)

| Request | Content | Value (RDL 016) | Confidence |
|---|---|---|---|
| `1A 8A` | Hardware / config ID | 28 bytes `00 37 44 60 44 03 10 ff …` | 🟢 Proven |
| `1A 8B` | Software modules (ASCII) | `KRTE49B0 HDTE16A0 EBTE87A0 CDTE91A0 KWTP11A0` | 🟢 Proven |
| `1A 8D` | VIN (ASCII) | `SALLXXXXXXXXXXXXX` | 🟢 Proven (confirms decoding) |

## Open questions (🔴 / 🟡)

- 🔴 **`21 3B`** — polled by the factory tool, content not yet isolated.
- 🔴 **`21 44` valve voltages** — the 8 inlet/outlet valve voltages and pump
  relay/monitor bytes in the rich analog block are not labelled (only battery @12
  and ECU supply @13 are proven).
- 🟡 **Wheel order** for `21 43` (speeds) and `21 50` (sensor V) — assumed
  FR/FL/RR/RL, needs a spin-one-wheel test to confirm.
- 🟡 **Settings pairing** — which of `21 45/46/49/59` is which setting (test
  status / transport / ECU calibrated / suspension type) is unsolved; solve by
  differential (toggle one, watch one byte).
- 🔴 **Switch bits** in `21 42/48/56/58` — only any-door (`21 56` b0.0) is
  isolated; Neutral / Low Range / Diff Lock / Reverse / HDC / Shuttle / Plip
  bits are not.
- 🔴 **Output lamp tests** (T.C. / ABS / HDC / Brake / SLS / Offroad lamps) — the
  `31 xx` routines exist but were captured as garbage in the first session
  (baud clash); they must be re-logged in menu order.
- 🟡 **Stored vs live heights** — `21 54` is the *live* height; the *stored*
  calibration source has not been captured. `Store heights` writes calibration —
  do not touch.
- 🟡 **`82` before init** — our best-effort StopCommunication before the first
  init attempt is not something the factory tool ever sends; it fixed the Td5
  generalReject but is unvalidated against the car for SLABS specifically.

## Source map

| Concern | File |
|---|---|
| Module driver (init, faults, live, actuators) | `src/d2diag/slabs/slabs.py` |
| Fault-block decoder + anchors | `src/d2diag/slabs/faults.py` |
| Factory-tool menu ↔ coverage map | `src/d2diag/slabs/menu.py` |
| Signal store (source of truth for tags) | `src/d2diag/signals/slabs.json` |
| Dashboard data source (light poll) | `src/d2diag/web/sources.py` (`SlabsDataSource`) |
| Protocol write-up (evidence) | `references/slabs_protocol.md` |
| Display fault-number list | `references/slabs_fault_codes.md` |
| Factory-tool menu map | `references/reference_tool_menu_map.md` |
