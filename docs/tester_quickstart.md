# Discovery 2 Td5 diagnostics — Mac tester quickstart

A ~15-minute setup to read your Land Rover **Discovery 2 Td5** (K-line, pre-CAN) with a cheap
KKL cable. **Read-only** — nothing is written to the car by default.

## 0. What you need
- A **Mac** + a Discovery 2 **Td5** (diesel; this is a K-line, pre-CAN car).
- A **KKL 409.1 USB–OBD cable**. On a Mac an **FTDI FT232** chip is easiest (driverless);
  CH340 / CP210x need a small driver; **avoid Prolific PL2303** (flaky on modern macOS).
- Python 3.9+ (macOS ships `python3`; otherwise `brew install python`).

## 1. Check the cable is seen (before touching the car)
Plug the cable into a **USB port** (not the car yet) and run:
```bash
ls /dev/cu.usbserial-*      # or:  ls /dev/cu.*
```
You should see something like `/dev/cu.usbserial-1420`. **Note that path.**
- Nothing shown → the driver isn't installed for your cable's chip, or the chip is Prolific.
  Install the chip's macOS driver (FTDI/CH340/CP210x) and try another USB port.
- If macOS blocks it: **System Settings → Privacy & Security → Allow**.
- Always use `cu.*`, **never** `tty.*` (tty blocks on the Mac).

## 2. Get the code and install
```bash
git clone https://github.com/Leijoma/discovery2-diag.git
cd discovery2-diag
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 3. Prove it works with NO car
```bash
pytest -q                          # ~300 tests, no hardware needed — all should pass
python tools/dashboard.py --mock   # then open http://localhost:8080  (Ctrl-C to stop)
```
You should see a dashboard with mock live data moving. If that works, the software is fine.

## 4. Connect to the car
1. Cable into the car's **OBD socket** (under the dash, driver's side) **and** USB into the Mac.
2. **Ignition ON** (position II — engine off is fine, or running). Car **stationary**.
3. Find the port again: `ls /dev/cu.usbserial-*` → e.g. `/dev/cu.usbserial-1420`.

## 5. Read-only sanity check (the engine ECU)
```bash
python tools/verify_ecu.py td5 /dev/cu.usbserial-1420
```
Expected: `✓ established`, immobiliser status, **fault codes**, and live fuelling values.
This **writes nothing** to the car.

SLABS (ABS + air suspension) — **only answers while stationary**:
```bash
python tools/verify_ecu.py slabs /dev/cu.usbserial-1420
```

## 6. The live dashboard
```bash
python tools/dashboard.py --serial /dev/cu.usbserial-1420
```
Open **http://localhost:8080** → live tiles + gauges, a **Faults** tab (decoded), Inputs, etc.
Switch **TD5 / SLABS** in the header. (Or `--serial auto` to auto-detect the cable.)

## Safety
- **Read-only by default** — no writes, no clearing, no actuator commands.
- Ignition on, car **stationary** — especially for SLABS (its diagnostics go silent once you move).
- The **Outputs** tab (actuator tests) sits behind an explicit confirmation — leave it alone unless
  you know what a given test does.

## Troubleshooting
| Symptom | Fix |
|---|---|
| No `/dev/cu.usbserial-*` | Cable driver not installed / Prolific chip / try another USB port. FTDI is easiest on Mac. |
| `pip install` fails | Make sure the venv is active (`source .venv/bin/activate`) and Python is 3.9+. |
| "no valid frame" / can't establish | Ignition on? Right port? Cable fully seated in the OBD socket? Try again — fast-init sometimes needs a second attempt. |
| Works then stops on SLABS | Normal — SLABS diagnostics die once the car moves; read it stationary. |
| macOS "driver blocked" | System Settings → Privacy & Security → **Allow**. |

## Feeding results back
The value is the reverse-engineering: send the maintainer your **fault codes**, what worked/didn't,
and (if asked) raw captures. That grows the shared knowledge base for every Discovery 2.
