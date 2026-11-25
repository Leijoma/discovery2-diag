# Test backlog — the living plan for what to do next in the car

**This is the single reference for "what do we test next".** Before a session in the
car (or with a borrowed diagnostic tool), open this file and pick items by context tag.
After the session, route each result to its permanent home (table below), then move the
item down to **Resolved** with the date and the outcome. Nothing else in the repo is a
to-do list for car work — `TODO.md` covers code and infrastructure only.

Updated 2026-11-12.

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

**Update 2026-11-25.** `21 50` (sensor voltage) is settled by a sensor-unplug test on a D2 V8
(GitHub issue #3): FR, RL, FL, RR, with RL by elimination. The store now assumes the same index
for `21 43`, so this test now only checks `21 43`.
- **Decision rule.** The spun wheel's field moves, and it is the one the store names → `21 43`
  is proven. Any other field moves → the two LIDs use different orders; fix `21 43` alone.
- **A cheap RL check without a jack.** Unplug only the RL sensor and read `21 50`. Byte 1 = `00`
  proves RL. The fault bit 5.5 should also set (clear it afterwards).

#### T-23 `[idle]` `[drive]` — SLABS hold: does a held session survive driving? (fault onset order)
**Why.** The owner's "four amigos" (ABS/TC/HDC + red brake lamp) light intermittently on most
drives and clear at the next ignition cycle. The logged block `21 11` has read `020` + `027` on
every one of 296 reads since 2026-08-31 (Influx `slabs.flog`) and `21 47` (current) has **never**
been non-zero. That is because we only reach SLABS after an ignition cycle at a standstill, when
the lamps have already cleared. The 2026-08-29 finding (Resolved) used **excursions**, which open
a *new* StartCommunication every time. It proves SLABS refuses new connections once the car has
moved. It does **not** test whether a session opened at a standstill and kept alive survives.
What we want is the **order** the SLABS faults appear in (does `020` trigger `027`, or the
reverse, or are they independent?).

**Procedure.** There are two ways to run it. Both use the same loop and cadence, one request/s:
`21 47` every 2 s, bare `3E` and `21 43` every 4 s, `21 11` about every 32 s. Neither logs engine
data during the run.
- **Mac (no flashing needed, preferred for the first run):**
  `PYTHONPATH=src python3 tools/slabs_hold.py auto` with the KKL cable. The ESP node must be
  muted or unplugged first. Or use `... /dev/cu.<esp> --esp` through the node's USB port, where
  the node yields the bus on its own. Prints edges live, writes `logs/slabs_hold-*.csv`, and
  **Enter** stamps a lamp mark (type e.g. `4 braking` first). The loop is
  `d2diag.slabs.hold`, unit-tested in `tests/test_slabs_hold.py`.
- **ESP node:** Settings → **SLABS hold: ON** (`/slabshold?on=1`). It logs to Influx. The setting
  is persisted, so every drive is a run until it is switched off. The firmware has **not been
  compiled yet** (no toolchain on the dev Mac 2026-11-12), so compile and OTA it before relying
  on it.
1. Ignition cycle, standstill, engine running. Wait for "SLABS held".
2. **Stand still for 2 min first.** If the session dies here, the cadence is the problem, not the
   speed. Stop and fix that before driving.
3. Drive normally. Note the time and the situation (braking, bump, creeping) when the amigos light,
   and whether it is 3 or 4 lamps.
4. Read back, either from the Mac CSV (`kind`=up/down/edge/status/mark, the same fields) or from
   Influx: `slabs_hold` (`alive`, `up_s`, raw `w43`) and `slabs_fault` (`block`=cur/log, `bit`,
   `state`, `seq` orders edges within one second, `base`=1 means the bit was already set at
   connect).

**Decision rule (set before the test).**
- **Session dies when the car starts to move** (`alive=0` with `up_s` matching the moment you
  pulled away): proven that SLABS also closes an open session in motion. Then the onset order is
  out of reach over K-line. Fall back to clear-and-drive (B-011 in `../Discovery 2/02-backlog.md`:
  `14 FF FF` at a standstill, drive, ignition cycle, read `21 11`). That gives which codes per
  drive, not their order.
- **Session survives and `21 47` gets bits when the lamps light:** current faults captured live.
  The `slabs_fault` `cur` edges, ordered by `seq`, give the onset order. Check it against the
  lamp count (3 = `020` alone, 4 = `027` involved). Bits other than `3.4`/`10.4` are new anchor
  points for `src/d2diag/slabs/faultmap.json`.
- **Session survives but `21 47` stays zero while the lamps are lit:** `21 47` is not where the
  lamp-driving faults live. Keep the raw capture and look at the other SLABS LIDs before
  concluding anything.
- **Bonus, any surviving run:** `w43` in motion gives the first moving wheel-speed data (scale +
  wheel order, T-14) and shows whether the FR wheel drops out at a `020` onset.

**Run log, Mac + KKL, 2026-11-12 (still open: no fault was provoked while driving).**
`logs/slabs_hold-20261112-*.csv`, five starts.
- **The held session lights the lamps.** The owner saw a "many lamps" combination come on when
  the session opened and go off a few seconds after pulling away. So it is our diagnostic session
  that lights them, not a fault: `21 47` read all-zero on every poll while they were lit. Don't
  take lamps seen during a hold run as fault onsets.
- **The session dies in motion.** 15:05:34: alive at 47.5 s with the wheels turning (`21 43`
  `eb 01 d1 01 ea 01 cc 01`, against `7c 00` ×4 at a standstill), then 3 empty `21` replies, down
  at 55.5 s. 15:08:51: last standstill read at 23.4 s, down at 34.5 s, consistent with pulling
  away. Lamps off and session dead come together, which fits SLABS ending the diagnostic session
  above a speed threshold. That is the first decision-rule branch, so far unconfirmed on a drive
  where the amigos actually lit. Two later starts (15:08:18, 15:08:41) got no connection at all
  (moved without an ignition cycle, as expected).
- **Next:** one more run where the amigos light *during* the drive. If the session is already
  dead by then, close T-23 on branch 1 and rely on read-and-clear per start.

#### T-24 `[drive]` — Which SLABS code latches per segment, and is Td5 bit 25.5 the amigos?
**Question.** The amigos stay lit until the ignition is cycled, so the driver sees only the
first onset per cycle. Two things are open:
- Which SLABS code latches in each segment (020 = 3 lamps, 027 = 4).
- Whether the unnamed Td5 fault bit `25.5` (byte 25 = road speed / cruise) has anything to do
  with the lamps.

On 2026-11-14, `25.5` came on at 15:36:30, the one onset with a known time. But it also came
on 9 times over two drives, nearly always below ~25 km/h after slowing, and again after the
ignition cycle at 15:41 without the lamps. It has toggled on almost every drive since
September.

`25.5` is not peculiar to this car. openhood (github.com/tuffjocke/openhood, issue #1,
2026-11-24) found it **set on a 1999 Defender** with an early MSB ECU. The Defender also had
`15.6` and `23.7` set, and no source names any of the three. So it is a normal state of the
road-speed input on at least one other Td5, not a fault peculiar to this SLABS. That weakens
"`25.5` is the amigos" but fits "`25.5` reacts to a weak or missing wheel-speed signal" equally
well. The Defender's ABS layout differs, so this doesn't change the decision rule. A
Nanocom/Testbook reading that names the bit would settle it.

**Setup.** Node firmware from 2026-11-15:
- SLABS read ~12 s after boot, before TD5.
- Read-and-clear stored even without an uplink (flash spill).
- `slabs_rd` in the heartbeat.
- **Amigos** button: `mark,src=node|pi` with `lamps`.

SLABS clear at start must be ON.

**Procedure.**
1. Normal driving. When the amigos light, press **Amigos** with the lamp count.
2. At the next stop, cycle the ignition and stand still until `slabs_rd` ≥ 1 (~15 s).
3. Repeat for at least 5 marked onsets.

**Decision rule (written 2026-11-15, before the data).**
- **Per segment.** Each `slabs_clear.flog_before` belongs to the segment that ended at that
  ignition cycle.
  - 020 alone + 3-lamp mark → the lamp count is the code, as B-011 assumes.
  - 027 in a segment marked 3 → that assumption is wrong.
  - A code set again in a segment with no mark → it recurred while the lamps were already lit.
- **Td5 25.5.**
  - It is linked to the lamps if ≥ 4 of 5 marks fall within 10 s after a `25.5` ON edge.
  - It is not linked if fewer than 2 of 5 do.
  - Anything in between is inconclusive.
  - Account for the base rate: `25.5` is ON a large share of low-speed time, so compare
    against random timestamps in the same drives.

**Progress 2026-11-17 (evening; local CET = UTC+1, driver's times ±1 min).** Two onsets of
4 lamps, no button marks (times from the driver's log).
- **Segment 19:39–~19:48** (onset 19:44, 4 lamps). Read-and-clear at the 19:39 key-on found
  the log empty. The read at the ~19:48 key-on (5 min idle) found **020 alone**. That
  record was spilled without a clock and reached Influx stamped on arrival at 20:03:16. So
  this was 4 lamps with 020 alone, against B-011's "020 alone = 3".
  - Td5 `25.5` went ON at 19:44:14 while slowing 40 → 23 km/h. That is 2 of 2 known
    onsets so far, but it also went ON at 20:05 and 20:06 with no lamps reported.
- **Segment ~19:48–20:03** (onset 19:57, 4 lamps). The read at the 20:03 key-on found the
  log **empty**, so no SLABS code latched for this onset. Either the lamps came from a
  non-latching condition, or from another module.
  - Td5 data for 19:46–20:03 never reached Influx: the node was on `Discopi` without a
    clock. **The relay's quarantine has it** (read-only read on 2026-11-22), but only in Pi-clock
    time, which runs from a restored, unsynced clock. Anchoring on the arrival stop (last row,
    speed 3) against the 20:03 key-on after the 4-min stop puts real time at about Pi-clock
    + 2 min (±1 min).
    - One node boot (poweron, `slabs_rd=2`) stood ~10 min, with SLABS reads every 60 s, all
      zero after the clear. It then drove ~3 min.
    - `25.5` went ON at Pi 18:54:38, about 19:56:40 local, shortly after moving off. That fits
      the 19:57 onset within the ±1 min anchor.
    - `5.0` + `17.2` went ON at about 19:58:40. `nfaults` moves with these bits.
- Cranking after the 4-min stop gave a `wdt` reset at 20:04:47, as on 2026-11-14.
  (Re-read after 2026-11-21: this could also have been the loose charger, see below.)

**Progress 2026-11-21 (first drive, local 18:55–19:21).** The driver saw 4 lamps twice. Each
time they stopped soon after and cycled the ignition. Influx has no exact times, and the Pi
marks are stuck in the relay's quarantine (no Pi clock).
- The engine was off at 19:00:45–19:02:26. The read at the 19:02:33 key-on found **020
  alone**. The log was last cleared empty at 17:51:45.
- The next key-on was probably the 19:03:53 boot. SLABS was silent there (old firmware). The
  read at 19:44:22 found **020 alone** again, latched during the rest of drive 1.
- So **3 of 3** four-lamp onsets with a SLABS code have 020 alone, and one (11-17 19:57) had
  none. Per the decision rule, the "020 = 3 lamps, 027 = 4" assumption is wrong; the lamp count
  does not identify the code.
- Td5 `25.5` went ON at 19:03:26 (~23 km/h, slowing), shortly before the second stop. Without
  marks this cannot be scored.
- **Caveat on ignition cycles.** On 2026-11-21 the node rebooted five times while driving (drive
  2, 20–75 km/h): the USB charger feeding it had a loose contact. Before that was fixed, a node
  boot is not proof of an ignition cycle. Here the 19:00:45 engine-off and the driver's account
  carry the segmentation.

#### T-25 `[key-on]` — SLABS silent since 2026-11-12: the node or the module?
**Question.** SLABS has not answered a single StartCommunication since 2026-11-12 13:54Z.
That covers 3 drive days and every attempt, including 2026-11-17 at 10, 20 and 31 s after
key-on with the car standing still. The `sb` field shows only our own echo `81 29 F7 81 22`,
so TX and the bus are fine and TD5 answers as usual. Before 11-12, SLABS answered at most
standstill samples (69 on 2026-10-29).

The node's init code (`klineFastInit`, `slabsEstablish`) has not changed since 2026-08-29.
What changed since 11-12:
- Firmware: WiFi roaming with async scans, the Pi relay, the read-and-clear (it never ran),
  and the early SLABS sample.
- Car side: the T-23 held session on 11-12, and more amigos onsets.

SLABS has a narrower fast-init window than TD5 (`slabs_init_problem_brief.md`: TiniH must be
25 ± 1 ms). The node's TiniH is `delay(25)` + `Serial2.begin()` + write latency, and has never
been measured.

**Procedure.** Key-on, engine off, car never moved this cycle.
1. Node muted (Settings → Mute).
2. `PYTHONPATH=src python3 tools/verify_ecu.py slabs auto` with the KKL cable. Do 3 attempts.
3. If KKL fails too, cycle the ignition and try once more.

**Decision rule (written 2026-11-17, before the test).**
- KKL connects (C1 57 8F) → the module is fine and the node is the problem. Next: measure the
  node's TiniH on a scope or logic analyser, and make the pulse exact (busy-wait, keep the UART
  attached).
- KKL is silent as well → SLABS (car side) has stopped answering diagnostics. Route it to B-011
  in the car journal, with the amigos history.
- KKL connects only on a second ignition cycle → inconclusive; repeat on another day.

#### T-15 `[idle]` — ABS bleed commands, first live run
⚠️ **Brake system. Only during an actual brake bleed.** `abs_power_bleed(True/False)` and
`abs_module_bleed()` are proven from the sniff but have never been run from our code.
Verify each replies `71 22 20`. If only verifying without bleeding: pulse power_bleed
on→off, confirm the ack, and do **not** run the full module sequence.

### P4 — Other modules

#### T-26 `[key-on]` — V8 engine ECU (Bosch Motronic M5.2.1): which bus and protocol?
**Question.** The Discovery 2 V8 and the Range Rover P38 4.0/4.6 (1999–2002) use a Bosch
Motronic M5.2.1. No open source gives its address, init or services
(`docs/rover-v8/README.md`). Dealer-type tools (Nanocom/Blackbox, Lynx, Faultmate) read it,
and owners report mixed results with ELM327 generic OBD. Which of the standard ways does it
answer, and does anything open a Land Rover-specific channel? A tester with a V8 and an FTDI
KKL cable is available. SLABS, the airbag module and the BCU are the same modules as on our
Td5, so the existing `verify_ecu.py` covers those on his car.

**Procedure.** Ignition ON (position II), engine off, car stationary, nothing else on the OBD
port.
1. `PYTHONPATH=src python3 tools/verify_ecu.py airbag auto`. This proves that the cable and the
   bus work on that car.
2. `PYTHONPATH=src python3 tools/v8_probe.py auto` (~1.5 min, read only). Send back
   `logs/v8_probe_<time>.txt`.
3. If step 2 finds nothing at all, cycle the ignition, wait 30 s and run it once more.

**Decision rule (written 2026-11-25, before the test).**
- **5-baud 0x33 gives `08 08` / `94 94`** → generic OBD is ISO 9141-2. Positive `01 00` → a
  generic OBD source (PIDs + `03` codes) can be built straight away. Check the `48 6B <ecu>`
  source byte: that is the ECU's physical address, and the first one to try for an LR channel.
- **5-baud 0x33 gives `xx 8F`, or the functional fast init `C1 33` answers** → generic OBD is
  ISO 14230. The same applies, and the physical address comes from the reply header.
- **A physical fast init answers C1** (0x10/0x11/0x12/0x01) → our KWP2000 stack carries over
  directly. Positive `21 01` → start a LID sweep like the Td5's. `7F 21 33` → reads need
  SecurityAccess, and we need a sniff of a dealer-type tool. `7F 21 12/11` → no `21` service
  there; try `18`/`1A` next.
- **Only DS2 answers (`12 xx A0 …`)** → it is BMW DS2, and openhood's `bmw-ds2` profile shows
  the frame format.
- **Airbag answers but the probe finds nothing** → the M5.2.1 is not on pin 7 with any of these
  inits. Next: ask the tester to borrow a Nanocom/Lynx and passively sniff a session (a second
  cable as listener).
- **Airbag is silent too** → it is the cable or the connection, not the ECU. Repeat T-25's checks.

#### T-16 `[key-on]` — BCU: map the read-only auth boundary
**Question.** How much of the BCU is legible **without** SecurityAccess? First contact,
address `0x40`, keybytes `E5 8F`, EKA-behind-SA and the rolling seed are all already
settled (see Resolved and `references/valeo_bcu_capabilities.md`) — the seed→key is
unknown and we have stopped chasing EKA. What we have **never** tested is whether the
BCU's live inputs (doors, key-in, locking, indicators, `21 D8..E9/2C/2D`) and settings
(`21 C6..EB`) actually *require* auth, or whether only EKA does. The reference tool did
SA before every read out of habit, so the 2026-08-09 sniff cannot answer it. If the
inputs read unauthenticated, we get live BCU body data for the dashboard for free.

**Setup.** Read only — no writes, no key, no actuators. Ignition cycle (off → fob key →
on) to put the BCU in diagnostic mode. New tool:
```
PYTHONPATH=src python3 tools/bcu_scan.py --serial auto
PYTHONPATH=src python3 tools/bcu_scan.py --serial auto --stimulus "open the driver door"
PYTHONPATH=src python3 tools/bcu_scan.py --serial auto --full     # optional: sweep 21 00..FF
```
It sweeps each LID **twice in shuffled order**, fetches a seed up front to flag the
`21 CC` decoy, and classifies every response: **DATA** (positive, plausibly real),
**SEED-DECOY** (positive but just the current seed), **DENIED** (`7F..33`
securityAccessDenied), **NRC** (other negative, e.g. `31` = no such LID), **NO-RESPONSE**,
or **INCONSISTENT** (disagreed between passes = comms-flaky, not gating). `--stimulus`
does a baseline → change one input → re-read and prints which LIDs' bytes **moved**.

**Decision rule.**
- A LID in **DATA**, stable across both passes, whose bytes **move** under `--stimulus`
  = real live data readable without auth → add it to the BCU source (`web/sources.py`)
  and map the field as `kandidat`. This is the win condition.
- **DATA** but constant even under stimulus = a static/placeholder positive; record the
  bytes, do not map a live field yet.
- **DENIED** = genuinely auth-gated; note it and move on (we cannot unlock).
- **NRC 0x31** = LID not supported on this module (expected for most of a `--full` sweep).
- **INCONSISTENT / NO-RESPONSE on both passes** = do not conclude; the BCU init is flaky
  (~1 in 4). Re-run before calling anything gated. **Mix the order, never read a block
  as one time-ordered sweep** — the tool shuffles for exactly this reason.

**Route results** to `references/valeo_bcu_capabilities.md` (the auth-boundary table) and,
for any live field found, the signal store + a BCU `DataSource`. Never the EKA code.

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

- **2026-08-29 — SLABS diagnostics are STANDSTILL-ONLY (does it really die at speed?).** The ESP
  node sampled SLABS while driving 0–71 km/h, logging whether `81 29 F7 81` got a reply. SLABS
  answered `C1` at a standstill right after an ignition cycle, then went **silent the instant the
  car moved** (StartComm only echoed — no `C1`, no `7F 81 10`) and **did not recover when stopped**
  — dead until the next ignition cycle. So it's SLABS suspending diagnostics while the ABS is
  active, not our polling. Live ABS-sensor data while driving is therefore **unreachable over
  K-line** (analog tap needed). The node's SLABS excursion is now gated to `speed < 5 km/h`. See
  `references/slabs_protocol.md`.
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
