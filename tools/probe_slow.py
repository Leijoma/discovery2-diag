"""Bus scan with 5-baud slow init — look for modules (SLABS et al.) on the K-line.

    PYTHONPATH=src python3 tools/probe_slow.py /dev/cu.usbserial-12345678 [lo] [hi]

Fast init only reached the engine (0x13). The other D2 modules probably use 5-baud
slow init. This sends slow init to each address and reports the one that responds
(the ECU starts with a 0x55 sync byte + key bytes). Stationary, ignition on.
Each address takes ~2 s (the 5-baud frame is 10 bits × 200 ms).
"""
import sys
import time

from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x3F
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        print(f"slow-init scan 0x{lo:02X}–0x{hi:02X} (~{(hi-lo+1)*2.5:.0f} s)...")
        for addr in range(lo, hi + 1):
            try:
                resp = t.slow_init(addr)
            except Exception as exc:  # noqa: BLE001
                print(f"0x{addr:02X}: ERROR {type(exc).__name__}: {exc}")
                break
            if resp:
                kw = SerialTransport.parse_slow_init(resp)
                marker = f"  <-- SYNC! KW1={kw[0]:#04x} KW2={kw[1]:#04x}" if kw else ""
                print(f"0x{addr:02X}: {resp.hex(' ')}{marker}")
                hits.append((addr, resp))
            time.sleep(0.4)  # short silence between addresses
    finally:
        t.close()
    print("\n--- summary ---")
    if hits:
        for addr, resp in hits:
            print(f"  0x{addr:02X}: {resp.hex(' ')}")
    else:
        print("  no responses in the range.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
