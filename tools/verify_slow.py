"""Verify the slow-init hits — repeat + interpret the handshake byte by byte.

    PYTHONPATH=src python3 tools/verify_slow.py PORT [addr_hex ...]

A REAL ISO 9141 / ISO 14230 5-baud response: ``0x55`` sync + KW1 + KW2, and then
(after we've sent ``~KW2``) the ECU's ``~address`` acknowledgement. If ``~address``
is in the tail, the handshake is COMPLETE = a real module, not an artifact.
Repeats each address 3x to prove consistency. Stationary, ignition on.
Default addresses = the hits 0x18/0x33/0x40.
"""
import sys
import time

from d2diag.transport import SerialTransport


def interpret(addr: int, raw: bytes) -> str:
    if not raw or raw[0] != 0x55:
        return "no sync → silent/artifact"
    if len(raw) < 3:
        return "sync but too short (no KW)"
    kw1, kw2 = raw[1], raw[2]
    inv = (~addr) & 0xFF
    complete = inv in raw[3:]
    tag = "COMPLETE ✓ real module" if complete else f"INCOMPLETE (~addr {inv:#04x} missing)"
    return f"KW={kw1:#04x} {kw2:#04x}  {tag}"


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    gap = 8.0  # >= session timeout so the module has time to release and responds to the next init
    addrs = [int(a, 16) for a in sys.argv[2:]] or [0x18, 0x33, 0x40]
    t = SerialTransport(port, timeout=1.0)
    t.open()
    results = {}
    try:
        print("quiet 5 s first...")
        time.sleep(5)
        for addr in addrs:
            print(f"\n== 0x{addr:02X} (~addr {(~addr)&0xFF:#04x}) ==")
            oks = 0
            for i in range(3):
                raw = t.slow_init(addr)
                txt = interpret(addr, raw)
                if "COMPLETE" in txt:
                    oks += 1
                print(f"  #{i+1}: {(raw.hex(' ') or 'silent'):18s} {txt}")
                time.sleep(gap)
            results[addr] = oks
    finally:
        t.close()
    print("\n--- VERDICT (complete out of 3) ---")
    for addr, oks in results.items():
        verdict = "REAL MODULE" if oks >= 2 else ("flaky/uncertain" if oks == 1 else "artifact/silent")
        print(f"  0x{addr:02X}: {oks}/3 complete → {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
