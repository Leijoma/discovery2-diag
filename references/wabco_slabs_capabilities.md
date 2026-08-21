# Wabco SLABS (Discovery 2) — diagnostic capabilities

Functional reference for the future **SLABS layer** in d2diag. Describes *what*
the Wabco SLABS controller exposes diagnostically (signals, expected values,
tests) — **not** the raw protocol (address/init/service bytes are still unknown,
see below).

**Source:** a commercial vendor / reference tool module **SM016 "WABCO SLABS"** (capability
description), plus the reference tool "Wabco SLABS – System Overview". Facts
(signal names, voltage ranges, states) compiled here into our own structure;
no text copied verbatim.

## About the controller
- Combined controller: **ABS + SLS + EBD + ETC + HDC + EAS** in one unit, sharing
  sensors/valves. Located behind the glovebox. Present on **all** D2s (air- or
  coil-sprung — the `Suspension type` flag decides).
- Internally divided into **modules** (Diagnostic, Measurement, ABS, EBD, HDC, Traction),
  each with its own reference code — can be changed independently.
- **Comms die >8 km/h** (all four wheels) — by design, no way around it. **All reading
  stationary.** Reached via the OBD socket (pin 7, shared K-line — see the platform's
  other notes).

## Capabilities (five groups)

### 1. Read fault codes
Reads the SLABS fault memory. Faults are listed as **Current** or **Intermittent** + the
**number of times detected**. Up to **47 fault types**. ⇒ Ideal for the intermittent
"three amigos": the counter survives even after a restart.

### 2. Clear fault codes
Clears the fault memory.

### 3. Settings (read/write identity + configuration)
Identity (read): Factory code, Bar code, Product number/date, module codes
(Channel/Safety/Diagnostic/Measurement/ABS/EBD/HDC/Traction), **VIN**, Engine type
(only with the engine running), Gearbox (only running).
Status/config (some writable): **ECU condition** (new-born/used, not reversible),
Test status, **Transport mode**, **Calibrated**, **Suspension type** (air/coil —
the only difference from a plain ABS ECU), **Left/Right current height** (0–255, ~1.4 mm
per step), Left/Right stored height (writable; read as N/A).

### 4. Inputs — live data (real-time)
**Voltages** (stationary OK):

| Signal | Expected (active / idle) |
|---|---|
| Wheel-speed sensor (FR/FL/RR/RL) — DC level | **2.0–2.4 V** |
| Inlet/outlet valve | 2.8–3.6 V / 0–0.5 V |
| Pump monitor | 2.9–3.8 V / 0–0.2 V |
| Pump relay | 2.8–3.6 V / 0–0.5 V |
| HDC brake relay | 2.8–3.6 V / 0–0.5 V |
| Ground reference | −0.5…+1 V |
| Rear height-sensor supply (L/R) | 4.7–5.6 V |
| L/R rear air-suspension valve, compressor relay, exhaust valve | (measured) |
| Internal ECU supply, Battery voltage | (measured) |

**Switches / speed / values** (change with movement; comms die >8 km/h):
height sensor value L/R (~1.4 mm/step), wheel speed per wheel (cannot measure <1.8 km/h),
switches (off-road, HDC, neutral [never GND on manual], diff lock, reverse, low range,
door), **RPM** (cannot measure <300 → show 0), Throttle angle (degrees), Engine torque (Nm).

Two extra state signals with defined states:
- **Shuttle** (the brake master cylinder's shuttle valves): `OPEN CIRCUIT` (wiring/connector
  broken), `BOTH OPEN` (brake released, HDC/ETC-controlled), `ONE CLOSED` (transition/light
  braking), `BOTH CLOSED` (brake pressed, ABS-controlled), `SHORT TO GROUND` (fault).
- **Plip signal** (from the BCU): `GROUND` (fault), `LOWER`, `NEUTRAL`, `RAISE`, `OPEN CIRCUIT` (fault).

### 5. Outputs — actuator tests (ON/OFF)
Instrument lamps (via the BCU): SLS, off-road, traction (TC), ABS, HDC (on/fault),
brake/EBD. **ABS valves**, **SLS valves**, air-suspension compressor, SLS buzzer,
**ABS pump relay**, **speedometer** (simulates 100 mph), **brake-light relay**.

### 6. Other functions
ABS power bleed, ABS modulator bleed, raise/lower rear left/right corner (corner
valve + inlet/exhaust), **Store heights** (save the current heights).

## Relevance for the "three amigos" (ABS/TC/HDC)
The register's cause list maps directly onto readable SLABS data:
1. **Wheel-speed sensor** → sensor voltage (2.0–2.4 V) + km/h per wheel, live.
2. **Shuttle valve contact** → the `Shuttle` state directly.
3. **SLABS controller** → fault codes (Current/Intermittent + counter) + valve/pump voltages.
The actuator tests (ABS valves, pump relay) can confirm suspected hardware.

## Remaining gap (to implement)
The raw protocol is **not** public: the SLABS **diagnostic address**, **init type**
(fast/slow 5-baud), **baud** and **service bytes** for read/clear/inputs/outputs.
Must be obtained via bus scan (pin 7, stationary) or sniffing before a
`d2diag` SLABS layer can be built. The KWP2000 layer, the tolerant read and the
pattern from the Td5 layer are reusable once address/init are known.
