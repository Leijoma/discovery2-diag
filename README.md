# Discovery 2 Td5 — Open Diagnostic Platform

An open, modular diagnostics platform for the Land Rover Discovery 2 Td5. The
D2 is a little too old for CAN bus, so it talks to its control modules over
**K-line**. With a cheap OBD2-to-USB cable (~€20–30) this project speaks that
protocol from your own computer — no proprietary tool required.

The goal isn't just another fault-code reader: it's a **library** where the Td5
is the first implementation, but the layered architecture is meant to extend to
other modules, vehicles and protocols. There's also a mobile-friendly web
dashboard on top so it's usable in the driveway from a phone.

> ⚠️ **Hobby / research project.** Reverse-engineered from bus traffic and
> community documentation. It reads a lot reliably, but it is not a finished
> product like a commercial tool. Use at your own risk; see the safety notes.

## What it can do today

- **Read & clear fault codes** — TD5 and SLABS (ABS + self-levelling air
  suspension) are proven against the car; SRS/airbag is **experimental** and
  strictly read-only.
- **Live engine data** from the TD5 ECU — rpm, coolant/air/fuel temperatures,
  manifold (boost) pressure, battery, accelerator tracks, injector balance, …
- **SLABS actuator tests** — ABS pump, per-wheel valve tests and the **ABS
  bleed procedure**, ride-height raise/lower, compressor, exhaust valve, buzzer.
- **BCU** — read the EKA (emergency key access) code and other settings.
- **Web dashboard** — a mock mode to explore without a car, and a live mode that
  talks to the vehicle; switchable at runtime. Plus a "Faults" tab that reads
  the fault memory from every module in one click.
- **Reverse-engineering tools** — a passive sniff decoder, an active
  differential-mapping harness, and a declarative signal store that turns each
  session into permanent, machine-readable knowledge.

ACE, the automatic gearbox (EAT) and BCU fault lists are partially
reverse-engineered but not yet decoded in code.

## Hardware

- A generic **OBD2-to-USB K-line cable** (KKL 409.1 style, FTDI FT232 / CH340 /
  CP210x). ~€20–30 on the usual sites. That's it.
- Optional, for **passive sniffing** of another tool's traffic: an ESP32 + an
  L9637D K-line front-end (RX-only), or an OBD splitter with pin 7 passed through.

## Architecture

A strict, bottom-up layer stack — each layer is decoupled and unit-tested:

```
Web dashboard   (stdlib HTTP + SSE, vanilla JS, mobile-first, zero deps)
Module layer    (Td5 · Slabs · Airbag — establish / read faults / live data / actuators)
KWP2000         (10/27/3E/21/30/31 · negative responses · responsePending · addressed mode)
K-Line          (framing addressed+unaddressed, checksum, fast + 5-baud slow init, retries)
Transport       (raw bytes in/out — no protocol knowledge; pyserial)
```

Supporting pieces: a **signal store** (`src/d2diag/signals/*.json`) read and
written by both the decoders and the auto-mapper, a passive **sniff** subsystem,
and the `web` dashboard. Nothing above the transport layer knows *how* the bytes
travel:

```python
from d2diag.transport import SerialTransport
from d2diag.kwp2000 import KWP2000
from d2diag.kline import KLine
from d2diag.td5 import Td5

td5 = Td5(KWP2000(KLine(SerialTransport("/dev/cu.usbserial-XXXX")), tolerant=True))
with td5:
    td5.establish()             # fast init → session → SecurityAccess unlock
    print(td5.read_faults())
    print(td5.read_all())       # decoded live data
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Tests run without hardware against a simulated half-duplex ECU (pyserial's
`loop://`), so you can hack on it with no car attached.

Run the dashboard:

```bash
# Try it with no car (mock data):
PYTHONPATH=src python3 tools/dashboard.py --mock

# Against the real vehicle (ignition on, stationary):
PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-XXXX
```

Then open <http://localhost:8080> — from the same machine, or from your phone on
the same network. You can switch mock ↔ live from the header. The machine with
the cable runs the server; the phone is just a browser (it never touches the
cable).

Read-only sanity check against a module:

```bash
PYTHONPATH=src python3 tools/verify_ecu.py td5   /dev/cu.usbserial-XXXX
PYTHONPATH=src python3 tools/verify_ecu.py slabs /dev/cu.usbserial-XXXX
```

### Serial port on macOS

`resolve_serial_port("auto")` finds the cable automatically
(`/dev/cu.usbserial-*`, `/dev/cu.wchusbserial*`, `/dev/cu.SLAB_USBtoUART*`), or
pass the port explicitly.

- Use **`/dev/cu.*`**, never `/dev/tty.*` — `tty` blocks waiting for carrier
  (DCD); `cu` (call-out) is correct for a KKL cable.
- **Drivers:** FTDI and CH34x are built into modern macOS. CH340 clones may need
  the WCH VCP driver; CP210x may need the Silicon Labs VCP.
- No `dialout` group / root needed for `/dev/cu.*` on macOS.
- FTDI's default 16 ms latency timer can jitter K-line fast init, but the
  tolerant `converse()`/`establish()` retry compensates — keep `tolerant=True`.

## Safety

K-line is a shared bus and this tool can *write* to ECUs. The design is
read-first and conservative:

- Fault reads and live data are read-only.
- Actuator tests (ABS pump, valves, air suspension) run only when you press the
  button, always behind a confirmation, and should be done **stationary with the
  ignition on**.
- **The airbag/SRS module is read-only by construction** — no clear, no outputs,
  no security writes. Never actuate pyrotechnic circuits.
- BCU output writes and the active mapping harness are gated / read-only by
  default.

## Status

- [x] Transport, K-Line (addressed + unaddressed framing, fast + slow init), KWP2000
- [x] Td5 — SecurityAccess seed→key, session, identifiers/scaling (validated on the car)
- [x] SLABS — faults, live data, actuator tests + ABS bleed. Connects on the first
      attempt since the fast-init pulse was corrected (2026-08-19): our TiniH was
      ~32 ms instead of the 25 ms ISO 14230-2 specifies, because the UART stop bit
      after the wake byte was unaccounted for and `time.sleep` overshoots. The Td5
      (Lucas) tolerated it for months; the Wabco module did not.
- [~] Airbag/SRS — read-only fault read (experimental, addressed framing at 0x5B)
- [~] ACE / auto gearbox (EAT) / BCU — partially reverse-engineered
- [x] Web dashboard, signal store, sniff decoder, active differential mapping

220 unit tests, all passing, run without hardware.

## Contributing

If you're equally nerdy — building something similar, have useful documentation,
or want to help develop and test — contributions of **data, mappings, docs or
code** are very welcome. Verifying every mapping (warning lights, sensor values,
status bits) against the car is slow, so extra hands and extra cars help a lot.
Open an issue or a pull request.

## Credits & references

This project stands on other people's work. Full licenses and exactly what was
used are in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

- **seed→key** (immobiliser SecurityAccess): ported from
  [pajacobson/td5keygen](https://github.com/pajacobson/td5keygen) (BSD-2-Clause).
- **protocol reference** (framing, ECU addresses, init/session, identifiers,
  fault-code map): [EA2EGA/Ekaitza_Itzali](https://github.com/EA2EGA/Ekaitza_Itzali)
  — protocol facts only, no code copied. Credits there to OffTrack (ECU
  disassembly) and Luca72 (Arduino reference).
- **K-line front-end** (fast-init timing, burst reads, L9637D):
  [muki01/OBD2_K-line_Reader](https://registry.platformio.org/libraries/muki01/OBD2%20K-Line) (MIT).
- **Td5 fault-code text**: cross-validated against a public, community-maintained
  Td5 fault-code list (offset/bit → fault text only).
- Thanks to the **Land Rover community** (forums and shared notes) for fault
  codes, menu structures and protocol tips that made the reverse engineering
  possible.

Contributing data or code? Add yourself here.

## License

MIT (see `pyproject.toml`). Third-party components retain their own licenses —
see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
