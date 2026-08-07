"""SLABS live-verktyg — läs/rensa/ställdon mot bilen (KRÄVER sändande kabel).

    PYTHONPATH=src python3 tools/slabs.py PORT [kommando]

kommandon:  faults (default) · vin · versions · clear · buzzer

⚠️ Kräver en SÄNDANDE K-line-interface (KKL, eller ESP32 i master-läge) — den
passiva sniff-tappen (RX-only) räcker INTE. Stillastående, tändning PÅ.
`buzzer` = ofarlig skriv-verifiering (hörbar). `clear` nollställer felminnet.
Protokoll: se references/slabs_protocol.md.
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
        print(f"etablerar SLABS (fast init 0x{SLABS_ADDRESS:02X})...")
        c1 = slabs.establish()
        print(f"  ✓ uppkopplad, C1-nyckelbytes {c1.hex(' ')}")
        slabs.tester_present()

        if cmd == "vin":
            print("VIN:", slabs.read_vin())
        elif cmd == "versions":
            for v in slabs.read_software_versions():
                print("  ", v)
        elif cmd == "clear":
            slabs.clear_faults()
            print("felminnet rensat (14 FF FF). Läser om:")
            print(" ", slabs.read_faults())
        elif cmd == "buzzer":
            print("aktiverar SLS-summer (skriv-verifiering)...")
            slabs.buzzer()
            print("  ✓ kommando skickat (hörde du summern?)")
        else:  # faults
            f = slabs.read_faults()
            print("LOGGADE fel:", f["loggade"] or "inga")
            print("AKTUELLA fel:", f["aktuella"] or "inga")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
