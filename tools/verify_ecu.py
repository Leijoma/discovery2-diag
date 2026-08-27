"""Active READ-ONLY verification against an ECU (requires a TRANSMITTING cable).

Establishes a session, reads fault codes and live data — **writes nothing** (except
an optional buzzer behind ``--buzzer`` + confirmation). Verifies that our d2diag layer
talks to the car correctly and that the decoding is right.

    PYTHONPATH=src python3 tools/verify_ecu.py td5   /dev/cu.usbserial-XXXX
    PYTHONPATH=src python3 tools/verify_ecu.py slabs /dev/cu.usbserial-XXXX
    PYTHONPATH=src python3 tools/verify_ecu.py slabs /dev/cu.usbserial-XXXX --buzzer
    PYTHONPATH=src python3 tools/verify_ecu.py td5   /dev/cu.usbserial-0001 --esp   # over an ESP node

The transport is swappable: a KKL cable (default) or an ESP32 in USB cable mode (--esp,
esp32/kline_node) — same stack either way, so the ESP frees the KKL cable to lend out.
Ignition ON, car stationary. SLABS comms die above ~8–20 km/h.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.kline import KLine  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.transport import EspTransport, SerialTransport  # noqa: E402


def _hex(b) -> str:
    return b.hex(" ")


def _transport(port: str, esp: bool):
    # Same Transport ABC either way — the diagnostic stack is front-end-agnostic.
    return EspTransport(port) if esp else SerialTransport(port, timeout=1.0)


def _kwp(port: str, target: "int | None" = None, esp: bool = False) -> KWP2000:
    kline = KLine(_transport(port, esp), target=target) if target is not None \
        else KLine(_transport(port, esp))
    return KWP2000(kline, tolerant=True)


def verify_td5(port: str, buzzer: bool = False, esp: bool = False) -> int:
    from d2diag.td5 import Td5
    t = Td5(_kwp(port, esp=esp))
    t.open()
    try:
        print("TD5: establishing (fast init 0x13 → session A0 → security)…")
        c1 = t.establish()
        print("  ✓ established, C1:", _hex(c1))
        print("  immobiliser status:", t.security_status(), "(0x03 = not immobilised)")
        print("\nFault codes (21 3B):")
        for f in t.read_faults() or ["(none)"]:
            print("  -", f)
        print("\nFuelling (live, decoded):")
        for k, v in sorted(t.read_all().items()):
            print(f"  {k:16} = {round(v, 3)}")
    finally:
        t.close()
    return 0


def verify_slabs(port: str, buzzer: bool = False, esp: bool = False) -> int:
    from d2diag.slabs import SLABS_ADDRESS, Slabs
    s = Slabs(_kwp(port, target=SLABS_ADDRESS, esp=esp))
    s.open()
    try:
        print("SLABS: establishing (fast init 0x29)…")
        c1 = s.establish()
        print("  ✓ established, C1:", _hex(c1))
        print("  VIN:", s.read_vin())
        print("  versions:", ", ".join(s.read_software_versions()))
        f = s.read_faults()
        print("\nFault codes:")
        print("  logged:", f["loggade"] or "(none)")
        print("  current:", f["aktuella"] or "(none)")
        print("\nLive data (raw — for scale verification against slabs_protocol.md):")
        names = {0x54: "height L/R", 0x53: "sensor supply L/R", 0x55: "compressor?",
                 0x43: "wheel speed ×4", 0x44: "analog block (valves/battery)",
                 0x49: "?", 0x50: "ABS sensor V ×4", 0x57: "CAN-derived"}
        for lid, name in names.items():
            try:
                d = s.read_data(lid)
                print(f"  21 {lid:02x} {name:26} = {_hex(d)}")
                s.tester_present()
            except Exception as exc:  # noqa: BLE001
                print(f"  21 {lid:02x} {name:26} = ERROR: {type(exc).__name__}: {exc}")
        if buzzer:
            if input("\n⚠️  Sound the SLS buzzer (write verification)? [y/n]: ").strip().lower() in ("y", "yes", "j", "ja"):
                s.buzzer()
                print("  buzzer sent ✓")
    finally:
        s.close()
    return 0


def verify_bcu(port: str, buzzer: bool = False, esp: bool = False) -> int:
    from d2diag.bcu import BCU_ADDRESS, Bcu
    b = Bcu(_kwp(port, target=BCU_ADDRESS, esp=esp))   # 5-baud slow init, unaddressed session
    b.open()
    try:
        print("BCU: 5-baud slow init to 0x40 (tip: needs an ignition cycle to connect)…")
        kw = b.establish(progress=lambda m: print("   ", m))
        print(f"  ✓ slow-init handshake OK, keybytes {kw[0]:02X} {kw[1]:02X}")
        print("\nIdentity (1A xx) — ASCII part/software id proves it is the BCU:")
        for k, v in b.identify().items():
            txt = "".join(chr(c) if 32 <= c < 127 else "." for c in v)
            print(f"    1A {k} = {_hex(v):32}  {txt!r}")
    finally:
        b.close()
    return 0


def verify_airbag(port: str, buzzer: bool = False, esp: bool = False) -> int:
    from d2diag.airbag import AIRBAG_ADDRESS, Airbag
    # Airbag is addressed framing throughout (unlike TD5/SLABS/BCU). Read-only by construction.
    a = Airbag(KWP2000(KLine(_transport(port, esp), target=AIRBAG_ADDRESS), tolerant=True, addressed=True))
    a.open()
    try:
        print("AIRBAG: 5-baud slow init to 0x5B → StartDiagnosticSession…")
        kw = a.establish()
        print(f"  ✓ established, keybytes {kw[0]:02X} {kw[1]:02X}")
        print("\nSRS fault codes (read-only — no clear, no outputs):")
        for f in a.read_faults() or ["(none)"]:
            print("  -", f)
    finally:
        a.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Active read-only ECU verification")
    ap.add_argument("module", choices=["td5", "slabs", "bcu", "airbag"])
    ap.add_argument("port")
    ap.add_argument("--buzzer", action="store_true", help="SLABS: offer a buzzer test (write)")
    ap.add_argument("--esp", action="store_true",
                    help="talk over an ESP32 in USB cable mode instead of a KKL cable")
    args = ap.parse_args()
    fn = {"td5": verify_td5, "slabs": verify_slabs,
          "bcu": verify_bcu, "airbag": verify_airbag}[args.module]
    try:
        return fn(args.port, args.buzzer, args.esp)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Check: right port? ignition on? transmitting cable? vehicle stationary?", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
