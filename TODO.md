# TODO — discovery2-diag

Updated 2026-08-19. Check off when done.

> **Scope:** this repo is the tool. The car's actual faults and maintenance
> work are handled in the sister project `../Discovery 2/` — fault codes we
> read out belong there, not here.

## Status

TD5 and SLABS both work reliably since the init pulse was corrected 2026-08-19
(TiniH was ~32 ms instead of 25 ± 1 — see `references/slabs_protocol.md`).
The dashboard connects to both on the first attempt and switches module without
trouble. 220 tests green.

## Next time in the car

- [ ] **Verify SLABS across several occasions.** The fix has been tested over a
      single afternoon. Run `tools/slabs_probe.py --quiet 5 --hold 30 --no-td5` on
      cold start, after longer standstill and in the cold. The hit rate should stay
      around 50 %+ per attempt, and the dashboard should connect on the first attempt.
- [ ] **Lower `retry_sleep`.** SLABS `establish` waits 28 s between attempts — a
      legacy from when init failed for timing reasons. Try 3–5 s and measure; probably
      unnecessary now and makes reconnect needlessly sluggish.
- [ ] **Decide W5 and P4.** Both are implemented but disabled and unproven:
      `--init-idle 1000` and `--write-gaps 0,5` respectively. The P4 measurement was
      also made before the wait became exact, so it measured the wrong value.
- [ ] **Read more SLABS LIDs now that the session is reliable.** Open per
      `slabs_protocol.md`: analog scaling for `21 53/55` (supplies), `44/49/57`
      (valves/voltages), `50` (ABS-sensor V), and the settings LIDs where
      LID→function is unsolved (requires differential: change ONE setting, see which
      raw byte moves).

## Code / offline

- [ ] **ACE, EAT and BCU** — material exists in the sniffs but is unimplemented.
      EAT ReadFaults is confirmed: `72 05 04 00 73` → `72 09 60 01 00 00 00 00 1B`
      (the response's meaning unknown — don't interpret as a fault counter yet).
- [ ] **Airbag** is read-only and experimental; unverified live.
- [ ] **Distinguish comms glitches from real sensor faults** (found 2026-08-21
      analysing two Td5 drive logs). Signals that share a LID are read in ONE
      request, so a bad read corrupts them together; a single bad signal whose
      LID-mates are valid is a real per-channel (sensor/wiring) fault. Concretely
      `air_temp`, `coolant_temp`, `fuel_temp` all live in **LID 0x1A**:
      - **whole-LID corrupt** (all its signals out-of-range / read failed) = a
        **comms** glitch — our tolerant K-line read occasionally drops a whole LID
        (~1 % baseline). Should be flagged/filtered, not counted as a sensor fault.
      - **one signal out-of-range while LID-mates are valid** = a real **sensor/
        circuit** fault — corroborate with the ECU's own DTC (e.g. `inlet air temp
        circuit (Current)`). On the motorway log 130/131 air_temp dropouts were of
        this kind + 126 ECU DTC rows = genuine intermittent IAT fault; on the
        evening log 6/6 were whole-LID = pure comms, 0 DTC.
      - **Action:** tag snapshots/CSV rows with a `comms_glitch` marker when a whole
        LID reads bad, and have the analysis classify junk as comms vs sensor (and
        cross-check the DTC). Stops us mistaking tool noise for a car fault. Belongs
        to the car register only as the *conclusion*, not the mechanism.
- [ ] **PyInstaller distribution** (.app/.exe) for non-technical users.
- [ ] **Torque proxy:** find the TD5's fuel quantity/demand LID (mg/stroke = the
      ECU's torque command, in the same session as rpm/temp/throttle).
- [ ] Translate code comments and docstrings to English (the code is in Swedish).
- [ ] Possibly reintroduce store-driven SLABS reading — but within the 1 Hz budget,
      which is what makes the session stable.

## Pi (discopi)

- [ ] Key-based login (`ssh-copy-id`), static IP, working `discopi.local`.
- [ ] Deploy the repo, run `pytest`, start the dashboard → reach it from the phone in the car.

## Hardware

- [ ] **ESP32 in master mode** — the sketch exists (`esp32/kline_test/`) and
      bit-bangs the pulse with microsecond precision. No longer necessary for SLABS,
      but the only way to measure the **physical** edges (we only see our software side)
      and a more stable alternative to USB-KKL.
- [ ] OBD splitter with pin 7 wired through for continued sniffing.

## Method lessons (cost a whole day 2026-08-19)

- **Never lock an experiment to one variant before the question is settled.** A run
  locked to `physical/F7` gave 0/50 and looked as if the module had stopped responding.
- **Mix the order.** A fixed variant order meant we measured the attempt number and
  thought it was the addressing mode.
- **Don't run conditions as separate time blocks** — then you measure the clock. A
  "significant" difference (p=0.017) turned out to be two different points in time.
- **Measure what you claim to measure.** Several hypotheses fell because the measured
  value contained something else (the echo in the burst, the burst read in `to_frame_ms`,
  `sleep` overshoot in P4).
