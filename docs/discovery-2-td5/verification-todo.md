# Verification backlog — Td5

Open items to move from 🟡 **Assumed** / 🔴 **Unknown** toward 🟢 **Proven**, and new
capabilities to confirm. This is the test list; results feed back into
[engine-td5.md](engine-td5.md). Contributions from other Td5s very welcome — if you
run any of these, record the numbers and the car.

All tests: **stationary, handbrake on**, ignition on. Output/actuator tests are
engine-off unless stated. The dashboard raw-logs everything, so most confirmations
just need a normal drive plus `tools/raw_analyze.py <raw-log>` afterward.

## 1. Fuel consumption (from injection quantity) 🔴 → 🟢

**Goal:** find the injection-quantity field and compute fuel use.

- **Capture:** a **loaded** drive — motorway/uphill, hold throttle in a high gear so
  load is high at moderate rpm. (Free-revving won't separate it; injection quantity
  tracks *load*, not just rpm.) Keep the dashboard on TD5.
- **Find the field:** `raw_analyze` the log; look in the `21 1D` block ("fuel-usage
  params" per Ekaitza) for a byte/u16 that rises with **load** and is distinct from
  the rpm-only fields. Candidates seen rising with rpm at free-rev: `1D` byte1, byte11.
- **Confirm scale:** injection quantity should read roughly single-digit mg/stroke at
  idle. If a reference tool is available, cross-read "Injection Quantity (mg/stroke)".
- **Compute** (5-cylinder 4-stroke, diesel ≈ 0.832 g/ml):
  ```
  fuel_flow[L/h] = injQty[mg/stroke] × 2.5[inj/rev] × rpm × 60 / 1e6 / 0.832
  economy[L/100km] = fuel_flow[L/h] / speed[km/h] × 100
  ```
  Sanity: ~8 mg/stroke @ 750 rpm ≈ 1.1 L/h idle. Record idle + steady-cruise numbers.
- **Deliverable:** map `injection_qty` into the signal store (🟢 once scale confirmed),
  add derived `fuel_rate` (L/h) and `economy` (L/100km) fields to the dashboard.

## 2. MAF scale fine-tune 🟡 → 🟢

`21 1D@5` is confirmed as MAF in kg/hr (69 idle → 184 @2000). To promote the *scale*
from forum-matched to car-proven: **cross-read a reference tool** "MAF" value at idle and
2000 rpm on RDL 016 and compare to our raw byte. Adjust scale/bias if needed.

## 3. EGR / wastegate position — `21 37 / 21 38` 🟡 → 🟢

Now raw-logged every cycle. **Confirm they respond** (non-error) and that the value
tracks behaviour:
- **EGR (`37`):** should move with the EGR modulator; blip throttle / vary load.
- **Wastegate (`38`):** should move with boost/load.
- If they track, map as `egr_position` / `wastegate_position` (÷100 → %). Relevant to
  RDL 016's EGR fault `001-07`.

## 4. Digital inputs / switches — `21 1E` (and `21 36`) 🔴 → 🟢

Bitfields for brake, clutch, cruise, A/C (Ekaitza pin map: brake B10/B16, clutch B35,
cruise B15/B17/B11, A/C B9/B23, transfer A33). **Toggle each physical input** while
watching the raw `1E`/`36` bytes; note which bit changes for each:
- Press/release brake pedal → bit?
- Press/release clutch → bit?
- Cruise on/off/set → bit?
- A/C request on/off → bit?
Deliverable: a bit→switch map, then decode as boolean signals.

## 5. VIN / ECU identity — `1A 87`, `1A 9A` 🔴 → 🟢

Add a ReadEcuIdentification read. Confirm `1A 87` returns a plausible VIN (ASCII) and
`1A 9A` the ECU type. Surface in the dashboard (read-only).

## 6. Map the remaining fuelling-block bytes 🔴

`21 1D / 1E / 1F / 20` all respond; several bytes move with rpm. With the loaded-drive
log from (1), `raw_analyze` the whole block and identify what each moving byte is
(injection timing? fuel demand? boost demand?). Record findings here with confidence.

## 7. Confirm wastegate modulator output — `30 BE` 🟡 → 🟢

We have the EGR modulator (`30 BD`) proven; the wastegate modulator (`30 BE FF 00 0A
13 88`) is from Ekaitza captures but never run from our code. Confirm it drives the
wastegate (engine off, listen/observe), behind explicit confirmation.

---

### How to contribute a result
Run a test, note the car (reg/variant/year), the raw values, and how you confirmed
them, and open a PR/issue updating the relevant row here and in `engine-td5.md`. A
result on a *different* Td5 is especially valuable — it tells us what is
model-general vs RDL 016-specific.
