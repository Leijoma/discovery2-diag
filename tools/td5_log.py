"""Log Td5 live data in a loop while the car is driven.

    PYTHONPATH=src python3 tools/td5_log.py /dev/cu.usbserial-12345678 [num_iterations]

Connects once and reads a selection of LIDs per iteration (the reads keep the session
alive). Robust against occasional noisy reads. Reads fault codes at the end.
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Td5
from d2diag.transport import SerialTransport

SAMPLE_LIDS = [0x09, 0x0D, 0x1C, 0x1A, 0x40, 0x10]  # rpm, speed, pressure, temp, balance, battery
SHOW = [
    "rpm", "speed", "manifold_press", "coolant_temp", "air_temp",
    "balance_1", "balance_2", "balance_3", "balance_4", "balance_5", "battery",
]


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    td5 = Td5(KWP2000(KLine(SerialTransport(port, timeout=1.0)), tolerant=True))
    with td5:
        c1 = td5.establish()
        print(f"connected {c1.hex(' ')} — logging {iters} iterations (rpm/speed/pressure/temp/balance)\n")
        t0 = time.monotonic()
        for _ in range(iters):
            row: "dict[str, float]" = {}
            for lid in SAMPLE_LIDS:
                try:
                    row.update(td5.read_lid(lid))
                except Exception:  # noqa: BLE001 — noisy read, skip this field
                    pass
            t = time.monotonic() - t0
            body = "  ".join(f"{k}={row[k]:.1f}" for k in SHOW if k in row)
            print(f"[{t:5.1f}s] {body}")
        print("\n--- fault codes after the run ---")
        try:
            named = [f for f in td5.read_faults() if not f.startswith("byte")]
            for f in named:
                print(f"  {f}")
            if not named:
                print("  no named faults")
        except Exception as exc:  # noqa: BLE001
            print(f"  fault read failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
