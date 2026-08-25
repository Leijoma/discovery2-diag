# Test backlog — the living plan for what to do next in the car

**This is the single reference for "what do we test next".** Before a session in the
car (or with a borrowed diagnostic tool), open this file and pick items by context tag.
After the session, route each result to its permanent home (table below), then move the
item down to **Resolved** with the date and the outcome. Nothing else in the repo is a
to-do list for car work — `TODO.md` covers code and infrastructure only.

Updated 2026-08-25.

## How to use it

1. **Pick by context.** Every test carries the conditions it needs:
   `[drive]` moving, `[idle]` stationary with the engine running, `[key-on]` ignition on
   engine off, `[lift]` a wheel safely off the ground, `[tool]` a borrowed reference tool
   (Nanocom), `[offline]` no car needed.
2. **Run it.** Each item states the exact command, what to watch, and — importantly —
   the **decision rule**: what result means what. A test without a decision rule in
   advance is how we end up measuring the clock (see the method lessons in `TODO.md`).
3. **Route the result.** Then update this file: outcome + date, and move it to Resolved.

### Where results go

| Result | Home |
| --- | --- |
| LID → field mapping, scaling, confidence | `src/d2diag/signals/*.json` via `upsert_field` — never hand-edited |
| Protocol facts (framing, init, services, timing) | `references/<module>_*.md` + the summary in `references/protocol_state_handoff.md` |
| Verdicts on external repos/claims | `references/td5_externa_fynd.md` |
| Fault codes and the car's actual condition | the sister project `../Discovery 2/` — **not** here |
| Raw captures | `logs/` (gitignored; scrub VIN/EKA before anything is published) |

### Standing rules

- K-line is a shared bus: **one module at a time**, always ending with `release()` (`82`).
- SLABS must be polled lightly — see `references/slabs_protocol.md`.
- Airbag/SRS is **read-only**. No outputs, ever.
- macOS: `/dev/cu.*`, never `/dev/tty.*`.
- Anything that moves the car or actuates brakes: handbrake on, nobody underneath.

---

## Open tests

### P1 — Td5 air/boost mapping (the biggest open question)

#### T-01 `[idle]` `[drive]` — Is `21 1C`@4 the measured MAF?
**Question.** `1C`@4 sat in the store as the unscaled `maf_raw` candidate until commit
`bba77a9` moved `maf` to `1D`@4 with a provisional 2-point calibration.
BinOwl_Td5Gauge names `1C`@4 as MAF, u16/10 kg/h. In our logs `1C`@4 is zero in
502/503 samples (rare junk blips up to 51080) across idle, load and >2500 rpm — but
RDL 016 has `air flow circuit (Current)` live, so a dead sensor reading zero with
occasional garbage is exactly what we would expect. That would make `1D`@4 a
*modelled* air mass shown under a measured name. Background:
`references/td5_externa_fynd.md`.

**Setup.** Td5 session, CSV logging + raw log on. Read the **whole** `21 1C` block
(8 data bytes), not just @0 — and log `1D`@4 in the same cycle.

**Procedure.** Idle 30 s → hold ~2000 rpm 30 s → one full-load pull if driving.
Best case: do it on a Td5 with a healthy MAF, or after the air-flow fault is fixed.

**Decision rule.**
- `1C`@4 non-zero and roughly 55–65 kg/h at idle, ~185–200 at 2000 rpm →
  `1C`@4 = **MAF (belagt)**; `1D`@4 gets renamed to a modelled air mass and its
  invented scale/bias dropped.
- `1C`@4 still zero-with-blips while `1D`@4 tracks load → consistent with the dead
  sensor; **inconclusive**, both stay `kandidat`. Do not "fix" it by rescaling.
- `1C`@4 moves but nowhere near kg/h → it is something else. Record the range and
  stop guessing at a scale.
- Fastest possible answer: **T-19** — one MAF reading off a reference tool screen
  settles it without any of the above.

#### T-02 `[drive]` — Cross-check the two wastegate mappings
**Question.** We have `1D`@17 (u8 ×100/255 %, `kandidat`). BinOwl and SimonRafferty
independently claim `21 38` = wastegate modulator (u16/1000 %). Our idle capture has
`04 61 38 00 00` = 0.0 %, which is compatible but does not discriminate.

**Procedure.** Same drive as T-01. Add `21 38` (and `21 37`) to the read set and log a
boost pull: steady cruise → full-load pull to ~3500 rpm → overrun.

**Decision rule.** If `38`/1000 and `1D`@17 ×100/255 agree within a few percent across
the pull, **both** are confirmed and `38` becomes the preferred (natively scaled) source.
If they diverge, the one matching the published band (0 % idle, 20–40 % on boost, max
~40 %) wins; the other gets demoted. If `37` moves too, it is the EGR counterpart —
compare against `1D`@15.

#### T-03 `[drive]` — Name the `21 1D` fuelling fields
**Question.** BinOwl maps `1D`@0 = driver's fuel demand and `1D`@14 = idle fuel demand
(both u16 ×0.01, same scale as our proven `injection_qty` at @6). @14 was previously
"varies but unidentified".

**Procedure.** In the same log: idle (no pedal) → steady pedal → **overrun** (lift off in
gear) → idle again.

**Decision rule.** @0 should follow the pedal and drop to ~0 on overrun; @14 should be
roughly constant and only meaningful at idle (it is the governor's demand). If they
behave that way, write both to the store as `kandidat` with this test as the source.

#### T-04 `[idle]` — What is `21 1C`@6?
Constant `0x009C` (156) in every capture we have. Watch it across cold start, warm idle,
load. If it never moves it is a reserved byte — record that and stop looking.

#### T-05 — EGR Inlet %, still unlocated
`1D`@15 = EGR modulator is a solid candidate; `1D`@16 is a constant-0 dead byte, so the
Nanocom page order misleads here. `1D`@14 is now claimed as idle fuel demand (T-03), so
the remaining unknown bytes in `1D` need a differential drive. Low priority until T-01/02
are settled.

### P2 — Td5 read-only additions (cheap, no risk)

#### T-06 `[key-on]` — ECU identification `1A xx`
We never read `1A`. Ekaitza gives `1A 87` = VIN, `1A 9A` = ECU type, `1A 9B/9C` = further
IDs. Read all four once, note the framing and lengths.
⚠️ **The response contains the VIN** — the raw log must be scrubbed before it goes
anywhere public (`references/hex-PII` rule: hex-encoded VIN survives text scans).

#### T-07 `[key-on]` — Injector classification codes
Five-character codes per injector, in a Settings/identifier block the dashboard never
polls, so they are in **no** raw log we have. Needs a targeted read. Useful for the car
register (injector matching), not for live data.

#### T-08 `[key-on]` — TD5 switch bit fields `21 1E` / `21 36`
Still open. `1E` toggles `00 CA`↔`00 EA` (bit `0x20`); `36` sat constant `00 0D`.
Differential procedure: connect, then actuate **one at a time**, annotating the log:
brake pedal → clutch → cruise on/off → A/C request → transfer box high/low.
**Decision rule.** A bit that flips exactly with one actuation is that switch (`belagt`).
A bit that flips with two different actuations is not identified — repeat.

#### T-09 `[tool]` — `21 3D` feature/config block
14-byte status block, read in bulk with `21 3D 20 0E 32 24`. To decode it we need the
reference tool's **Settings → Feature/config** screen: all 21 ENABLED/DISABLED flags in
displayed order plus ECU Status. Read them off the screen; no sniff needed.

### P3 — SLABS

#### T-10 `[idle]` — Confirm session reliability across occasions
The init-pulse fix has only been tested over one afternoon. Run on cold start, after a
long standstill, and in the cold:
```
PYTHONPATH=src python3 tools/slabs_probe.py --quiet 5 --hold 30 --no-td5
```
**Decision rule.** ≥50 % hit rate per attempt and the dashboard connecting on the first
attempt = reliable, close the item. Anything worse: keep the raw logs, do not tune blind.

#### T-11 `[idle]` — Lower `retry_sleep`
SLABS `establish` waits 28 s between attempts, a legacy from the broken-timing era. Try
3–5 s and measure the hit rate over ~10 attempts. **Rule:** keep the shorter wait only if
the hit rate is statistically indistinguishable — and mix the order, do not run the two
settings as separate time blocks.

#### T-12 `[idle]` — Decide W5 and P4
Both implemented, disabled, unproven: `--init-idle 1000` and `--write-gaps 0,5`. The P4
measurement predates the exact wait, so it measured the wrong thing. Re-measure or delete
the flags — do not leave them as dead options.

#### T-13 `[idle]` — Scale the remaining SLABS analog LIDs
Open per `references/slabs_protocol.md`: `21 53/55` (supplies), `44/49/57`
(valves/voltages), `50` (ABS-sensor V). Read within the 1 Hz budget. For the settings
LIDs where LID→function is unsolved, the only method is differential: change **one**
setting, see which raw byte moves.

#### T-14 `[lift]` — Prove the wheel order
`wheel_speed_fl/fr/rl/rr` is a **hypothesis**. Jack up ONE wheel safely (axle stands,
handbrake, engine running, SLABS connected), spin it by hand, see which field moves.
Repeat for a second wheel → then the byte order is proven. Without jacking, it stays a
candidate — do not promote it on plausibility.

#### T-15 `[idle]` — ABS bleed commands, first live run
⚠️ **Brake system. Only during an actual brake bleed.** `abs_power_bleed(True/False)` and
`abs_module_bleed()` are proven from the sniff but have never been run from our code.
Verify each replies `71 22 20`. If only verifying without bleeding: pulse power_bleed
on→off, confirm the ack, and do **not** run the full module sequence.

### P4 — Other modules

#### T-16 `[key-on]` — BCU / EKA
First contact. Read only. Requires an ignition cycle (off → key → on → key).
```
PYTHONPATH=src python3 tools/bcu_probe.py --expect XXXX
```
Three informative outcomes: reference value found (EKA encoding proven → document the
**encoding** in `references/valeo_bcu_capabilities.md`, never the code — public repo);
`securityAccessDenied` (the probe fetches a seed → keep `logs/bcu_probe-*.raw.log`, it is
the input to the unknown Valeo keygen); or no contact on `0x40` (try `--address 0x18` and
cycle the ignition again). The `1A` response should contain a readable Valeo part number
if `0x40` really is the BCU.

#### T-17 `[idle]` — Autobox (EAT) read faults
The one module we have never got fault codes out of. Engine **running**, selector in
**P/N**. Framing is solved (`72 <len> <data> <XOR-cs>`) and `72 05 04 00 73` →
`72 09 60 01 00 00 00 00 1B` is confirmed — but the response's meaning is unknown, so do
not interpret it as a fault count yet. Note verbatim what comes back.

#### T-18 — Airbag live verification
Implemented, addressed framing at `0x5B`, read-only by construction, **never verified
against the car**. A single successful establish + read-faults is all that is needed.
⚠️ Read only. No outputs.

### P5 — Needs a borrowed reference tool `[tool]`

#### T-19 — Screen values to correlate against raw bytes
We already have the raw bytes for most blocks; what we lack is the tool's plain-text
values. Highest value, no sniffing required — write down **all** values in **displayed
order**:
- SLABS → ABS Inputs (wheel speeds, ABS sensor V, valves, pump monitor/relay, battery,
  ECU supply, ground ref, HDC brake, engine speed/torque/throttle) → vs `21 43/44/49/50/57`
- SLABS → SLS Inputs (L/R height, sensor supply, L/R volts, exhaust valve, compressor
  relay) → vs `21 53/54/55`
- TD5 → Settings → Feature/config → solves T-09
- TD5 → the MAF/air-flow live value → **settles T-01 directly**

#### T-20 — Fault read across all modules
Per-module checklist with the exact wording to note down:
`references/fault_read_checklist.md`. Codes go to the sister project.

### P6 — Offline `[offline]`

#### T-21 — Decode `21 0E` / `21 32` (homologation / map variant)
We already hold the bytes: `61 0e 73 73 75 75 74 74 64 64 70 70 30 30 30 30 38 38` —
ASCII with every character doubled ("ssuuttddpp00008 8"). Work out the field split and
what the variant string means; no car needed.

#### T-22 — Distinguish comms glitches from real sensor faults
Signals sharing a LID are read in one request, so a bad read corrupts them together.
Whole-LID corrupt = comms glitch (~1 % baseline); one signal bad while its LID-mates are
valid = a real sensor/circuit fault, corroborated by the ECU's own DTC. Tag CSV/snapshot
rows with a `comms_glitch` marker and classify in the analysis. Detail in `TODO.md`.

---

## Resolved

Move items here with the date and what actually settled them — including the ones that
came back inconclusive, so we do not re-run them blind.

- **2026-08-23 — ESP32 K-line node talks to the Td5.** Wiring proven: L9637D VS on pin 7,
  pull-up 510 Ω–1 k is critical, common ground required.
- **2026-08-21 — `accel_way3` moves (0 → 2.23 V).** Pedal track 3 is live; `1B` mapping
  confirmed against the car. (Note: BinOwl's frame-length heuristic labels our 12-byte
  `1B` the "MSB" variant, which disagrees with the Euro-3/NNN reading — harmless for us,
  unresolved in general. See `references/td5_externa_fynd.md`.)
- **2026-08-21/22 — `1D`@15 EGR modulator and `1D`@17 wastegate modulator** confirmed
  across four drives as behaviour (not scale). `1D`@16 is a constant-0 dead byte.
  Scale still `kandidat` → T-02.
- **2026-08-21 — `1D`@6 = injection quantity (mg/stroke), `belagt`,** via deliberate
  overrun lifts: idle 11.1 → load 23.9 → overrun 4.7 (below idle = fuel cut).
- **2026-08-20 — `21 21` = idle-governor error (s16),** ≈0 at idle, grows with engine
  speed. Not a fault.
- **2026-08-19 — SLABS init pulse corrected** (TiniH was ~32 ms instead of 25 ± 1); both
  modules connect reliably. Follow-up on repeatability → T-10.
- **2026-08-18 — the communication link outlives the process.** A run that only talks to
  SLABS is still rejected if a previous run died with the link open — hence the
  best-effort `82` before every init attempt.
- **2026-08-03 — `1A` temperatures and `1C`@0 boost** verified against the car
  (coolant 59.2 °C; boost 1.0 → 1.2 bar). `1A`@8 "ext_temp" is a phantom: the sensor is
  not fitted, so it reads a constant 150.0 °C.

---

## Detailed procedures kept elsewhere

These predate this file and hold step-by-step detail worth keeping. This backlog is the
index; they are the appendices.

- `references/biltest_plan_slabs_bcu.md` — SLABS signals, ABS bleed, BCU probe (full commands)
- `references/fault_read_checklist.md` — per-module fault reading with a reference tool
- `references/final_session_plan.md` — the prioritized reference-tool session
- `references/reference_tool_sniff_plan.md` — sniffing the reference tool
- `references/bcu_sniff_plan.md` — BCU-specific sniffing
