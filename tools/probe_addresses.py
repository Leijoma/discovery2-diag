"""Bus scan: try fast init against all K-line addresses, report responses.

    PYTHONPATH=src python3 tools/probe_addresses.py /dev/cu.usbserial-12345678

On the D2 several control units share the K-line (pin 7). The engine = 0x13. This
looks for other modules (e.g. SLABS) that respond to fast init. Reports only
addresses whose burst contains a real response (C1 = positive, 7F = rejected-but-present).
Stationary, ignition on. (SLABS may require 5-baud slow init instead — then nothing
shows here, which is also an answer.)
"""
import sys
import time

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x3F
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        print(f"scanning 0x{lo:02X}–0x{hi:02X} (physical fast init, engine dormant, ~{(hi-lo+1)*1.4:.0f} s)")
        print("holding the line quiet for 20 s first...")
        time.sleep(20)
        # Skip 0x13: an open engine session generalRejects ALL addresses and
        # masks the other modules. Never address 0x13 → the engine stays dormant.
        for addr in [a for a in range(lo, hi + 1) if a != 0x13]:
            time.sleep(1.0)
            kl = KLine(t, target=addr)
            kl._fast_init_pulse()
            raw = kl.converse(b"\x81", addressed=True)
            # strip our echo (81 addr F7 81 cs) → look only at the response after
            echo = encode(b"\x81", target=addr, source=TESTER_ADDRESS, addressed=True)
            idx = raw.find(echo)
            resp = raw[idx + len(echo):] if idx >= 0 else raw
            if 0xC1 in resp or 0x7F in resp or resp.strip(b"\x00"):
                tag = "C1! POSITIVE" if 0xC1 in resp else ("7F" if 0x7F in resp else "noise/unknown")
                print(f"0x{addr:02X}: {tag}  response={resp.hex(' ')}")
                hits.append((addr, tag))
    finally:
        t.close()
    print("\n--- summary ---")
    for addr, tag in hits:
        print(f"  0x{addr:02X}: {tag}")
    if not hits:
        print("  no responses in the range — try another MODE (probe_scan.py: fast-f1/func/slow).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
