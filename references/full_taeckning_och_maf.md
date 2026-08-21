# Full data coverage + the MAF find (Td5)

Written 2026-08-21. The principle, method and concrete findings from the MAF hunt on RDL016.

## Principle: capture ALL received data, not just mapped fields

Every TD5 poll returns a whole data block per LID. The bytes we haven't named are exactly
where unmapped signals hide. Two parts:

1. **Poll everything the reference tool polls** — including LIDs we can't map yet, so the
   raw log captures them (see `web/sources.py`, `_TD5_COVERAGE_EXTRA` + `_SLABS_COVERAGE`).
2. **Analyze everything** — `tools/raw_analyze.py` reads a raw log and shows, per LID,
   which byte positions move, each u16 offset + correlation against RPM, and
   what is mapped vs unmapped.

## MAF found: `21 1D` byte 5 (u8, kg/hr) — PROVEN

**The method that cracked it:** raw data from a run with the rpm in motion
(`tools/lid_sweep.py --seconds 75`, idle→2000→2500), then **byte-level binning
against rpm** — not just u16. MAF turned out to be **ONE byte**, not u16.

Car test 2026-08-21 (RDL016, engine running):

| rpm | 1D byte5 |
|---|---|
| idle (~780) | **69** |
| ~2000 | **184** |

Tracks load (2.7×). Matches published Td5 reference tool ranges: idle 55–65, 2000 rpm
185–200, high load 3000 rpm 550–600, overboost cut ~618–650.

**The sensor is HEALTHY.** Contradicts the earlier "dead MAF" theory. Confirmed at the
connector (CO149, 3-pin): 12 V on pin 3, pin1–2 = 17 kΩ (reference ~16.8 kΩ), and the
live signal tracks rpm. `maf_raw` (1C@4 = 0 while running) was NEVER MAF but a status field.

## ext_temp = ghost (1A@8 constant 0x1088 = 150 °C)

An external temperature sensor is NOT fitted on the Td5 ECU. `21 1A@8` is a constant that
decodes to exactly 150.0 °C. The real outside temperature (~17 °C) comes from the car's own
cluster sensor via the BCU, not the engine ECU. The field has been given limits `[-40,50]` so
150 is flagged **suspect** (struck through) in the UI instead of looking like a temperature.

## Coverage implementation

- **TD5** (not session-sensitive): reads the confirmed-responding unmapped LIDs
  **1E, 1F, 20** every cycle (on top of the mapped ones), so they're sampled alongside rpm for
  future correlation. `1D` is now polled automatically because `maf` exists in the store
  (`LIDS` is derived from the store).
- **SLABS** (must be polled LIGHTLY — block reading kills the session, see
  `slabs_protocol.md`): the whole reference tool input block (`11,3B,42–59`) is rotated **ONE
  LID per cycle**; the 0x54 heights are read every cycle. Traffic stays ~1 Hz.

## Open / next steps

- **Broader LID discovery:** we know 1D–20 respond; a sweep over more TD5 LIDs
  (0x0E–0x40) may reveal more responding blocks to add to the coverage.
- **1D's other bytes move with rpm:** byte1 (27→65), byte11 (50→127) — probably
  fuel quantity/injection, unmapped. Now captured in the raw log every poll.
- Tools: `tools/raw_analyze.py <raw log>` (offline, all LIDs + rpm correlation),
  `tools/lid_sweep.py` (live, also reads unpolled LIDs + ranks against rpm).
