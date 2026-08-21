"""Find the right post-slow-init header format — try concrete raw frames against a module.

    PYTHONPATH=src python3 tools/probe_slow_fmt.py PORT ADDR_HEX

For each candidate frame: do a 5-baud slow init (own session), send the raw frame, dump
the WHOLE burst (junk included). A response with 0x7E (TesterPresent ACK) or 0x7F (neg)
reveals the right format. >=8 s between attempts (session lock). Stationary, ignition on.
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport


def cs(b: bytes) -> bytes:
    return b + bytes([sum(b) & 0xFF])


def candidates(addr: int):
    a = addr
    # TesterPresent (0x3E) in various KWP2000/ISO formats + tester addresses
    return [
        ("unaddr len-in-fmt      ", cs(bytes([0x01, 0x3E]))),
        ("addr fmt=0x81 F7       ", cs(bytes([0x81, a, 0xF7, 0x3E]))),
        ("addr fmt=0x81 F1       ", cs(bytes([0x81, a, 0xF1, 0x3E]))),
        ("functional C1 F1       ", cs(bytes([0xC1, a, 0xF1, 0x3E]))),
        ("addr+lenbyte 80..01    ", cs(bytes([0x80, a, 0xF7, 0x01, 0x3E]))),
        ("addr+lenbyte 80 F1     ", cs(bytes([0x80, a, 0xF1, 0x01, 0x3E]))),
        ("ISO9141 68 6A F1       ", cs(bytes([0x68, 0x6A, 0xF1, 0x3E]))),
        ("ISO9141 68 addr F1     ", cs(bytes([0x68, a, 0xF1, 0x3E]))),
        ("ISO9141 82 addr F1     ", cs(bytes([0x82, a, 0xF1, 0x3E]))),
        ("addr src=0x03          ", cs(bytes([0x81, a, 0x03, 0x3E]))),
    ]


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x40
    t = SerialTransport(port, timeout=1.0)
    t.open()
    kl = KLine(t, target=addr)
    hits = []
    try:
        print(f"quiet 6 s first...")
        time.sleep(6)
        for name, frame in candidates(addr):
            raw_init = t.slow_init(addr)
            if not (raw_init and raw_init[0] == 0x55):
                print(f"  {name} init silent, skipping")
                time.sleep(8)
                continue
            kl._flush_input()
            t.send(frame)
            burst = kl._burst_read(0.06, 1.2)
            i = burst.find(frame)
            resp = burst[i + len(frame):] if i >= 0 else burst
            mark = ""
            if 0x7E in resp:
                mark = "  <<< 7E ACK!"
                hits.append((name, "7E"))
            elif 0x7F in resp:
                mark = "  <<< 7F neg (response!)"
                hits.append((name, "7F"))
            print(f"  {name} TX {frame.hex(' ')} → {resp.hex(' ') or 'silent'}{mark}")
            time.sleep(8)
    finally:
        t.close()
    print("\n--- format hits ---")
    print("  " + (", ".join(f"{n.strip()}={tag}" for n, tag in hits) if hits else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
