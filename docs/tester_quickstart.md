# Discovery 2 Td5 diagnostics — Mac tester quickstart

A ~15-minute setup to read your Land Rover **Discovery 2 Td5** (K-line, pre-CAN) with a cheap
KKL cable. **Read-only** — nothing is written to the car by default.

## 0. What you need
- A **Mac** + a Discovery 2 **Td5** (diesel; this is a K-line, pre-CAN car).
- A **KKL 409.1 USB–OBD cable**. On a Mac an **FTDI FT232** chip is easiest (driverless);
  CH340 / CP210x need a small driver; **avoid Prolific PL2303** (flaky on modern macOS).
- Python 3.9+ (macOS ships `python3`; otherwise `brew install python`).

## 1. Cable pre-test — do this FIRST (no install needed)
This one-minute check tells you if the cable will work on your Mac *before* you install anything.
Just the cable + Terminal, **no car yet**:

```bash
ls /dev/cu.* > /tmp/before.txt          # snapshot BEFORE plugging in
# --- now plug the cable into a USB port, wait ~3 seconds ---
ls /dev/cu.* > /tmp/after.txt ; diff /tmp/before.txt /tmp/after.txt
```
- A **new line appears** (e.g. `> /dev/cu.usbserial-1420`, or `cu.wchusbserial…`, or
  `cu.SLAB_USBtoUART…`) → **the driver works, you're good.** Note that path — you'll use it later.
- **Nothing new** → the chip has no working driver yet. Identify the chip:
  ```bash
  system_profiler SPUSBDataType | grep -iE -A6 "serial|uart|ftdi|prolific|ch340|qinheng|cp210|silicon"
  ```
  The vendor tells you the chip → install that driver, then re-run the test:
  | Vendor in the output | Chip | macOS |
  |---|---|---|
  | FTDI (0x0403) | FT232 | works driverless — if not seen, try another USB port/cable |
  | QinHeng (0x1a86) | CH340 | install the CH340 macOS driver |
  | Silicon Labs (0x10c4) | CP210x | install the CP210x VCP driver |
  | Prolific (0x067b) | PL2303 | troublesome on modern macOS — driver often won't stick; consider a different cable |
- If macOS blocks a driver: **System Settings → Privacy & Security → Allow**, then re-plug.
- Always use `cu.*`, **never** `tty.*` (tty blocks on the Mac).

**Only proceed to step 2 once a `cu.usbserial-*` (or cu.wch…/cu.SLAB…) device appears.**

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
