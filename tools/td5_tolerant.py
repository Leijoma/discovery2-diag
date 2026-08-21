"""Td5 live data via the library's tolerant mode — thin wrapper.

    PYTHONPATH=src python3 tools/td5_tolerant.py /dev/cu.usbserial-12345678

The whole proven sequence (tolerant burst read + unlock) now lives in d2diag:
    Td5(KWP2000(KLine(SerialTransport(...)), tolerant=True)).establish()
Requires a fresh ECU (an ignition cycle just before). Ignition on, engine OFF.
"""
import sys

from d2diag.kline import KLine
from d2diag.kwp2000 import KWP2000, KWP2000Error, NegativeResponse
from d2diag.td5 import LIDS, Td5
from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    td5 = Td5(KWP2000(KLine(SerialTransport(port, timeout=1.0)), tolerant=True))
    with td5:
        try:
            c1 = td5.establish()
        except KWP2000Error as exc:
            print(f"Connection failed: {exc}")
            print(">> Run an ignition cycle and try again.")
            return 1
        print(f"CONNECTED & UNLOCKED — C1 {c1.hex(' ')}\n--- live data ---")
        for lid in LIDS:
            try:
                vals = td5.read_lid(lid)
            except (NegativeResponse, KWP2000Error) as exc:
                print(f"21 {lid:02X}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — noise-corrupted read, skip
                print(f"21 {lid:02X}: {type(exc).__name__}")
                continue
            body = ", ".join(f"{k}={v:.2f}" for k, v in vals.items())
            print(f"21 {lid:02X}: {body}")

        print("\n--- fault codes (21 3B) ---")
        try:
            faults = td5.read_faults()
        except (NegativeResponse, KWP2000Error) as exc:
            print(f"  fault read failed: {exc}")
        else:
            named = [f for f in faults if not f.startswith("byte")]
            for f in named:
                print(f"  {f}")
            if not named:
                print("  no named faults")
            generic = [f for f in faults if f.startswith("byte")]
            if generic:
                print(f"  ({len(generic)} undefined bits: {', '.join(generic)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
