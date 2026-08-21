"""Targeted fast-init test against SLABS candidate addresses (KWP2000 fast init).

    PYTHONPATH=src python3 tools/probe_slabs.py /dev/cu.usbserial-12345678

Evidence (LR forum + pyTD5Tester): the Wabco SLABS on the D2 is initialized with
**fast init**, not slow init. Concrete candidates from pyTD5Tester/TD5Tester:
  - physical fast init to 0x29, tester 0xF7:  81 29 F7 81 22
  - functional init to 0x34, tester 0xF1:     C1 34 F1 81 67
The engine (81 13 F7 81 0C) is run first as a control. Long silence before, and ≥5 s
between attempts (a slow-init module can otherwise interpret the low pulse as a
5-baud start). Stationary, ignition on. Looks for C1 (positive) or 7F (response-but-rejected).
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport

# The candidates FIRST (the engine stays dormant → no open engine session masks them);
# the engine control LAST (it opens the engine session, but by then the candidates are done).
CANDIDATES = [
    ("SLABS? fast init 0x29 (F7)",    bytes.fromhex("8129f78122")),
    ("SLABS? functional 0x34 (F1)",   bytes.fromhex("c134f18167")),
    ("engine 0x13 (control, LAST)",   bytes.fromhex("8113f7810c")),
]


def classify(raw: bytes, frame: bytes) -> "tuple[bytes, str]":
    """Pick the response AFTER our echo and classify (avoid a false C1 in the echo)."""
    idx = raw.find(frame)
    resp = raw[idx + len(frame):] if idx >= 0 else raw
    if 0xC1 in resp:
        return resp, "C1! POSITIVE RESPONSE"
    if b"\x7f\x81" in resp:
        return resp, "7F 81 (generalReject — probably the engine masking)"
    if 0x7F in resp:
        return resp, "7F"
    return resp, ("(no response)" if not resp.strip(b"\x00") else "noise/unknown")


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    kl = KLine(SerialTransport(port, timeout=1.0))
    with kl:
        for name, frame in CANDIDATES:
            print(f"holding the line quiet for 20 s (let any session die)...")
            time.sleep(20)
            kl._fast_init_pulse()          # 25 ms low + 25 ms high
            kl._flush_input()
            kl._t.send(frame)              # send raw candidate frame
            raw = kl._burst_read(0.06, 1.2)
            resp, tag = classify(raw, frame)
            print(f"{name:32s} TX {frame.hex(' ')} → response {resp.hex(' ') or 'silent'}  {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
