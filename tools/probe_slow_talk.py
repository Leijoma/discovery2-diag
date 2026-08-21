"""Talk to a slow-init module after establishing a session — identify it.

    PYTHONPATH=src python3 tools/probe_slow_talk.py PORT ADDR_HEX

Do a 5-baud slow init against ADDR, then send (in the same session) a battery of
KWP2000 requests and dump the raw response (hex + ASCII). Tries both unaddressed
and addressed header formats and reports whichever gives a response. Hunting for
identity: TesterPresent (keeps it awake), StartDiagnosticSession,
ReadEcuIdentification (1A xx), ReadDataByLocalIdentifier (21 xx). Stationary, ignition on.
"""
import sys
import time

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.transport import SerialTransport

# (name, payload) — ordered: wake/keep-awake first, then identity.
REQUESTS = [
    ("TesterPresent",        b"\x3e"),
    ("StartSession default", b"\x10\x81"),
    ("StartSession 0x85",    b"\x10\x85"),
    ("ReadEcuId 1A 80",      b"\x1a\x80"),
    ("ReadEcuId 1A 87",      b"\x1a\x87"),
    ("ReadEcuId 1A 9B",      b"\x1a\x9b"),
    ("ReadDataLocal 21 01",  b"\x21\x01"),
]


def ascii_of(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


def strip_echo(raw: bytes, frame: bytes) -> bytes:
    i = raw.find(frame)
    return raw[i + len(frame):] if i >= 0 else raw


def try_request(kl: KLine, addr: int, payload: bytes):
    """Send payload in BOTH header formats, return (format, response) for the one
    that yields something after echo stripping."""
    for addressed in (False, True):
        frame = encode(payload, addr, TESTER_ADDRESS, addressed=addressed)
        raw = kl.converse(payload, addressed=addressed, overall=1.2)
        resp = strip_echo(raw, frame)
        if resp.strip(b"\x00"):
            return ("addr" if addressed else "unaddr"), resp
        time.sleep(0.1)
    return None, b""


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x40
    t = SerialTransport(port, timeout=1.0)
    t.open()
    try:
        print(f"quiet 6 s, then slow init 0x{addr:02X}...")
        time.sleep(6)
        raw = t.slow_init(addr)
        kw = SerialTransport.parse_slow_init(raw)
        if not kw:
            print(f"  no session ({raw.hex(' ') or 'silent'}) — aborting")
            return 1
        print(f"  ✓ session: {raw.hex(' ')}  KW={kw[0]:#04x} {kw[1]:#04x}")
        kl = KLine(t, target=addr, source=TESTER_ADDRESS)
        for name, payload in REQUESTS:
            fmt, resp = try_request(kl, addr, payload)
            if resp:
                print(f"  {name:22s} [{fmt:4s}] → {resp.hex(' ')}   |{ascii_of(resp)}|")
            else:
                print(f"  {name:22s}        → (silent)")
            time.sleep(0.15)
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
