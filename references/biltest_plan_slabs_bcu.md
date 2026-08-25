# Car test — SLABS signals/bleeding + BCU/EKA (plan)

> **Appendix.** The living backlog of what to test next is `references/test_plan.md`;
> this file holds the step-by-step detail it points at.

Written 2026-08-19. Verifies the protocol changes since the last car test.
Run **stationary, handbrake on**. K-line is shared → one session at a time; the tools
release the session cleanly (`82`) themselves. Tick off in the log.

## Prerequisites

- SLABS connects best **with the engine running** (measured 2026-08-19). The init-pulse
  fix is in place, so connecting in 1–2 attempts is expected.
- BCU requires an **ignition cycle** (off → key → on) and can be run with the engine off.
- Be careful which port: `PYTHONPATH=src` is needed for `tools/*.py`.

---

## PART A — SLABS live signals (engine running, ~10 min)

Goal: confirm that the new fields decode reasonably, and capture raw data for the
candidates we can't scale yet.

### A1. Connect + capture a baseline CSV
```
PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-XXXX --slabs --csv
```
- Open `:8080`, switch to SLABS, let it sit ~1 min.
- **Check under Inputs (v2 at `/v2` if you want to test the new UI):**
  - `height_left/right` ~110–160, L≈R on level ground. ✅ if stable.
  - `wheel_speed_fl/fr/rl/rr` — all ~124 (raw value, ≠ km/h) stationary.
  - `abs_sensor_*` ~2.3 V.
  - `battery`/`ecu_supply` ~12.5–14 V.
  - `any_door` = closed; **open a door** → should become open. ✅ confirms the interlock.
- The CSV lands in `logs/livedata-*-slabs.csv` (rotated per module).

### A2. Wheel-order test (confirms fl/fr/rl/rr — HYPOTHESIS for now)
Requires a wheel that can be spun: **jack up ONE wheel safely** (axle stands, handbrake
on the others), engine running, SLABS connected.
- Spin the lifted wheel by hand and see **which `wheel_speed_*` field changes**.
- Note: lifted wheel = X → the field that moves is the correct name for X.
- Repeat for at least two wheels → then the whole byte order is proven (otherwise it
  stays a candidate).
- ⚠️ Without jacking up: skip this; the order stays a hypothesis.

### A3. MAF + accelerator pedal (for future scaling)
Still engine running, SLABS is the wrong module here — **switch to engine (TD5)** in the
UI (or run `--serial … ` without `--slabs`). With CSV logging on:
- **MAF:** note the `maf_raw` raw value at **idle** and at **~2000 rpm** (hold the
  accelerator steady for a while at each). Reference: idle 55–65 kg/hr, 2000 rpm
  ~185–200. We can then work out the raw-value→kg/hr scale from the two points.
- **accel_way3 (Euro 3 test):** press the accelerator down slowly and see if `accel_way3`
  moves. If it moves → the car is Euro 3 and the field is valid. If it stays at 0 → Euro 2,
  the field is a ghost channel (mark candidate/not applicable).
- **Accelerator mirroring:** confirm that `accel_way1` rises while `accel_way2` falls.

---

## PART B — SLABS ABS bleed (ONLY if you are actually bleeding brakes)

⚠️ **Brake system.** Only run this if you are doing a real brake bleed. Stationary,
handbrake, nobody under the car. The commands are proven from the sniff but never run
from our code against the car — this is the first time.

- In the dashboard (SLABS → ABS bleed section), or from Python:
  ```
  PYTHONPATH=src python3 -c "
  from d2diag.slabs import Slabs, SLABS_ADDRESS
  from d2diag.kwp2000 import KWP2000; from d2diag.kline import KLine
  from d2diag.transport import SerialTransport
  s=Slabs(KWP2000(KLine(SerialTransport('/dev/cu.usbserial-XXXX'),target=SLABS_ADDRESS),tolerant=True))
  s.open(); s.establish()
  s.abs_power_bleed(True)   # pump starts
  # ... bleed ...
  s.abs_power_bleed(False)  # stop
  s.abs_module_bleed()      # 4-step sequence
  s.release()"
  ```
- **Verify:** each command should reply `71 22 20` (the tool throws otherwise). Listen for
  the pump/valves. If it's only to be **verified without bleeding**: run `power_bleed`
  on→off quickly and confirm the ack, do NOT run the whole module sequence needlessly.

---

## PART C — BCU / EKA code (own session, ~5 min)

First time we connect to the BCU. Read only — no writes.

### C1. Run the probe with the reference value
```
PYTHONPATH=src python3 tools/bcu_probe.py --expect XXXX
```
It guides the ignition cycle (off → Enter → on → Enter), runs 5-baud slow init against
`0x40`, asks `1A xx` (who are you), and reads `21 CC` (EKA).

### C2. Three possible outcomes — all informative
1. **`REFERENCE FOUND`** → the EKA format is proven (one digit/byte or nibbles). Write the
   encoding into `references/valeo_bcu_capabilities.md` — but NOT the code (public repo).
2. **`securityAccessDenied` (7F … 33)** → EKA requires SecurityAccess. The probe then
   fetches a **seed** for you. Save `logs/bcu_probe-*.raw.log` — it's needed for the keygen
   work (Valeo seed→key is unknown).
3. **No contact on 0x40** → try `--address 0x18` (the other slow-init candidate), and cycle
   the ignition again.

### C3. Confirm the identity
The `1A` response should contain readable ASCII (Valeo part number) if `0x40` really is the
BCU. Note what came back — it settles the 0x40 guess.

---

## After the test
- Paste the tail of `logs/connection.log` + the relevant `bcu_probe`/`slabs_probe` logs.
- Update the confidence in the signal store for what was confirmed (wheel order, MAF scale).
- BCU findings → `references/valeo_bcu_capabilities.md` (code NEVER in the repo).
