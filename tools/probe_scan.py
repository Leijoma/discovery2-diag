"""Flexible module scan — try different init variants against an address range.

    PYTHONPATH=src python3 tools/probe_scan.py PORT MODE [lo] [hi]

MODE:
    fast-f7   physical fast init, tester 0xF7   (81 <addr> F7 81)
    fast-f1   physical fast init, tester 0xF1   (81 <addr> F1 81)
    func-f1   functional fast init, F1          (C1 <addr> F1 81)
    func-f7   functional fast init, F7          (C1 <addr> F7 81)
    slow      5-baud slow init (8N1)            → looks for 0x55 sync

The engine (0x13) is skipped (its open session generalRejects everything and masks
the bus). Long silence first + gaps between. Looks for C1/7F (fast/func) or 0x55 (slow)
AFTER our echo. Stationary, ignition on. Run one MODE at a time.

Recommended order next car test: fast-f1 → func-f1 → func-f7 → slow.
(fast-f7 0x01–0xFF is already negative.)
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport


def build_frame(mode: str, addr: int) -> "bytes | None":
    """Raw init frame (incl. checksum) for the mode, or None for slow."""
    if mode == "slow":
        return None
    tester = 0xF1 if mode.endswith("f1") else 0xF7
    fmt = 0xC1 if mode.startswith("func") else 0x81   # functional vs physical
    b = bytes([fmt, addr, tester, 0x81])
    return b + bytes([sum(b) & 0xFF])


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    mode = sys.argv[2] if len(sys.argv) > 2 else "fast-f1"
    lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x01
    hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0xFF
    if mode not in ("fast-f7", "fast-f1", "func-f7", "func-f1", "slow"):
        print(f"unknown MODE: {mode}")
        return 2

    t = SerialTransport(port, timeout=1.0)
    t.open()
    kl = KLine(t)
    per = 2.6 if mode == "slow" else 1.1
    hits = []
    try:
        print(f"scanning {mode} 0x{lo:02X}–0x{hi:02X} (~{(hi-lo+1)*per:.0f} s). Quiet 20 s first...")
        time.sleep(20)
        for addr in range(lo, hi + 1):
            if addr == 0x13:
                continue
            time.sleep(0.8)
            if mode == "slow":
                raw = t.slow_init(addr)
                if raw and 0x55 in raw:
                    print(f"0x{addr:02X}: SLOW-SYNC 0x55!  {raw.hex(' ')}")
                    hits.append((addr, "0x55"))
                continue
            frame = build_frame(mode, addr)
            kl._fast_init_pulse()
            kl._flush_input()
            t.send(frame)
            raw = kl._burst_read(0.06, 1.0)
            i = raw.find(frame)
            resp = raw[i + len(frame):] if i >= 0 else raw
            if 0xC1 in resp:
                print(f"0x{addr:02X}: C1! POSITIVE  {resp.hex(' ')}")
                hits.append((addr, "C1"))
            elif 0x7F in resp:
                print(f"0x{addr:02X}: 7F  {resp.hex(' ')}")
                hits.append((addr, "7F"))
    finally:
        t.close()
    print("\n--- hits ---")
    print("  " + (", ".join(f"0x{a:02X}={tag}" for a, tag in hits) if hits else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
