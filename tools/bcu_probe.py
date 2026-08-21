#!/usr/bin/env python3
"""BCU probe: connect to the Valeo BCU and read the EKA code. **Read only.**

The target is the EKA code (Emergency Key Access) — four digits entered via
the driver's door lock if the remote key stops working, which lets you bypass
the immobiliser. We read it; we never write.

The basis:
  * **Address `0x40`, 5-baud SLOW init.** Our address hunt on 2026-08-05 got a
    complete handshake with KWP2000 keys `E5 8F`. That it IS the BCU is an
    inference — the module answers with the ignition off, and the BCU is the only
    permanently powered D2 module. The script therefore asks the module who it is
    (`1A xx`) before anything else.
  * **EKA is read with `21 CC`** — proven from the sniff on 2026-08-09, where that
    frame was sent exactly once during the operator marker "read set eka".
  * **The response format is NOT proven** (the sniffed response was corrupt). The
    script shows the raw bytes and both plausible interpretations so you can compare
    against a known code.

⚠️ **An ignition cycle is required.** The BCU enters diagnostic mode on an ignition
transition. The reference tool asks the operator to turn the ignition OFF, press a
key, and then turn it ON. The script guides you through the same sequence.

    PYTHONPATH=src python3 tools/bcu_probe.py
    PYTHONPATH=src python3 tools/bcu_probe.py --address 0x18   # try another candidate
    PYTHONPATH=src python3 tools/bcu_probe.py --no-prompt       # skip the guidance
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from d2diag.bcu import BCU_ADDRESS, Bcu  # noqa: E402
from d2diag.bcu.bcu import EKA_LID, find_digits  # noqa: E402
from d2diag.kline import KLine  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.kwp2000.kwp2000 import NegativeResponse  # noqa: E402
from d2diag.transport import LoggingTransport, SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

_log_fh = None


def say(msg: str = "") -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}" if msg else ""
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def ascii_of(data: bytes) -> str:
    """Readable characters from a response — so a module that states a part number shows up directly."""
    txt = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return txt if any(c.isalnum() for c in txt) else ""


def main() -> int:
    global _log_fh
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto")
    ap.add_argument("--address", default=hex(BCU_ADDRESS),
                    help=f"diagnostic address (default {hex(BCU_ADDRESS)}; 0x18 is the other "
                         "slow-init candidate from the address hunt)")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--no-prompt", action="store_true",
                    help="skip the ignition-cycle guidance")
    ap.add_argument("--expect", metavar="CODE",
                    help="known EKA code (e.g. 1234) to search for in the response. With the "
                         "answer known the format need not be guessed — the script shows exactly "
                         "how the code is encoded. Passed as an argument and NEVER stored in the repo.")
    args = ap.parse_args()

    addr = int(args.address, 0)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    raw_path = f"logs/bcu_probe-{stamp}.raw.log"
    _log_fh = open(f"logs/bcu_probe-{stamp}.log", "w", encoding="utf-8")

    say(f"BCU probe {stamp} — address 0x{addr:02X}, 5-baud slow init")
    say(f"raw TX/RX → {raw_path}")
    say("READ ONLY: no writes, no key programming.")

    if not args.no_prompt:
        say()
        say("The BCU enters diagnostic mode on an IGNITION TRANSITION.")
        input("  1. Turn the ignition fully OFF, then press Enter …")
        input("  2. Turn the ignition ON (position II), then press Enter …")
        say("thanks — running init right away while the module is receptive")

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        say(f"no cable found: {exc}")
        return 1

    transport = LoggingTransport(SerialTransport(port, timeout=1.0), logfile=raw_path)
    try:
        transport.open()
    except Exception as exc:  # noqa: BLE001
        say(f"could not open {port}: {type(exc).__name__}: {exc}")
        return 1

    bcu = Bcu(KWP2000(KLine(transport, target=addr), tolerant=True))
    try:
        try:
            kw = bcu.establish(attempts=args.attempts, progress=lambda m: say(f"  {m}"))
        except Exception as exc:  # noqa: BLE001
            say(f"\n✗ no contact: {exc}")
            say("  Try: cycle the ignition again, or --address 0x18.")
            return 1
        say(f"\n✓ CONNECTED — keybytes {kw[0]:02X} {kw[1]:02X}")

        # 1) Who are you? Determines whether the 0x40 guess holds.
        say("\n[identity] asking the module who it is (1A xx)")
        ident = bcu.identify()
        if not ident:
            say("  no 1A responses — the module may not support ReadEcuIdentification")
        for opt, data in ident.items():
            say(f"  1A {opt}: {data[:24].hex(' ')}   {ascii_of(data[:24])}")

        # 1b) SecurityAccess SEED. The reference tool does 27 01 → 27 02 RIGHT after
        # connecting (sniff 2026-08-09), before every read. Without unlock the BCU
        # returns a fixed placeholder for everything (proven in the car 2026-08-20). We
        # cannot send the key — the Valeo seed→key is unknown — but we capture the seed
        # so it can feed future keygen work.
        say("\n[security] fetching a seed (27 01) — we cannot unlock yet, just capture")
        try:
            seed = bcu._kwp.request_seed(0x01)
            say(f"  seed: {seed.hex(' ')}  ← save the log; needed for Valeo keygen")
        except Exception as exc:  # noqa: BLE001
            say(f"  seed request did not respond ({type(exc).__name__})")

        # 2) The target: EKA. Without unlock this is likely a placeholder.
        say(f"\n[EKA] reading 21 {EKA_LID:02X}  (locked without SecurityAccess)")
        try:
            eka = bcu.read_eka()
        except NegativeResponse as exc:
            say(f"  ✗ denied: {exc}")
            if exc.nrc == 0x33:
                say("  securityAccessDenied → EKA requires SecurityAccess (27 01/27 02).")
                say("  The sniff shows the reference tool does it, but the seed→key algorithm")
                say("  for the BCU is unknown. Fetching a seed so we have data to work with:")
                try:
                    seed = bcu._kwp.request_seed(0x01)
                    say(f"    seed: {seed.hex(' ')}  ← save, needed for the keygen work")
                except Exception as sexc:  # noqa: BLE001
                    say(f"    seed request failed: {type(sexc).__name__}")
            return 1
        except Exception as exc:  # noqa: BLE001
            say(f"  ✗ read error: {type(exc).__name__}: {exc}")
            return 1

        say(f"  raw: {eka['raw'].hex(' ')}")
        say(f"  interpreted as one digit per byte:   {eka['bytes']}")
        say(f"  interpreted as two digits per byte: {eka['nibbles']}")
        say(f"  plausible interpretation: {eka['plausible']}")

        if args.expect:
            digits = [int(c) for c in args.expect if c.isdigit()]
            hit = find_digits(eka["raw"], digits)
            if hit:
                say(f"\n  ✓ KNOWN CODE FOUND in the response: encoding '{hit['encoding']}' "
                    f"at offset {hit['offset']} ({hit['bytes']})")
                say("    → the format is thereby proven. Write it into "
                    "references/valeo_bcu_capabilities.md (but NOT the code).")
            else:
                say("\n  ✗ known code not found — likely a LOCKED placeholder.")
                say("    The BCU gave the same data on 1A as on 21 CC → EKA is gated behind")
                say("    SecurityAccess (27 01/27 02), which we cannot do yet (Valeo")
                say("    seed→key unknown). The seed above is the first puzzle piece.")
        else:
            say("\n  Run with --expect <code> if you know the code, and the format is decided directly.")
        return 0
    finally:
        try:
            bcu.release()   # 20 + 82 — don't leave a session open on a shared bus
        except Exception:  # noqa: BLE001
            pass
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
