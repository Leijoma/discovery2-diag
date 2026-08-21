"""SLABS live tool — read/clear/actuators against the car (REQUIRES a transmitting cable).

    PYTHONPATH=src python3 tools/slabs.py PORT [command]

commands:  faults (default) · vin · versions · clear · buzzer · verify

⚠️ Requires a TRANSMITTING K-line interface (KKL, or ESP32 in master mode) — the
passive sniff tap (RX-only) is NOT enough. Stationary, ignition ON.
`buzzer` = harmless write verification (audible). `clear` resets the fault memory.
Protocol: see references/slabs_protocol.md.
"""
import sys

from d2diag.kline import KLine
from d2diag.kwp2000 import KWP2000
from d2diag.slabs import SLABS_ADDRESS, Slabs
from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    cmd = sys.argv[2] if len(sys.argv) > 2 else "faults"

    slabs = Slabs(KWP2000(KLine(SerialTransport(port), target=SLABS_ADDRESS), tolerant=True))
    with slabs:
        print(f"establishing SLABS (fast init 0x{SLABS_ADDRESS:02X})...")
        c1 = slabs.establish()
        print(f"  ✓ connected, C1 key bytes {c1.hex(' ')}")
        slabs.tester_present()

        if cmd == "verify":
            # Full read+write verification in one run.
            print("VIN:", slabs.read_vin())
            print("versions:", ", ".join(slabs.read_software_versions()))
            f = slabs.read_faults()
            print("logged faults:", f["loggade"] or "none")
            print("current faults:", f["aktuella"] or "none")
            print("WRITE test: sounding the SLS buzzer...")
            slabs.buzzer()
            print("  ✓ if you heard the buzzer: read AND write work live. 🎯")
        elif cmd == "vin":
            print("VIN:", slabs.read_vin())
        elif cmd == "versions":
            for v in slabs.read_software_versions():
                print("  ", v)
        elif cmd == "clear":
            slabs.clear_faults()
            print("fault memory cleared (14 FF FF). Reading back:")
            print(" ", slabs.read_faults())
        elif cmd == "buzzer":
            print("sounding the SLS buzzer (write verification)...")
            slabs.buzzer()
            print("  ✓ command sent (did you hear the buzzer?)")
        else:  # faults
            f = slabs.read_faults()
            print("LOGGED faults:", f["loggade"] or "none")
            print("CURRENT faults:", f["aktuella"] or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
