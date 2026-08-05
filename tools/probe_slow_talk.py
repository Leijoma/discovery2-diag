"""Prata med en slow-init-modul efter etablerad session — identifiera den.

    PYTHONPATH=src python3 tools/probe_slow_talk.py PORT ADDR_HEX

Gör 5-baud slow init mot ADDR, och skickar sedan (i samma session) en batteri
KWP2000-förfrågningar och dumpar råsvaret (hex + ASCII). Testar både oadresserat
och adresserat header-format och rapporterar det som ger svar. Söker identitet:
TesterPresent (håller vaken), StartDiagnosticSession, ReadEcuIdentification (1A xx),
ReadDataByLocalIdentifier (21 xx). Stillastående, tändning på.
"""
import sys
import time

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.transport import SerialTransport

# (namn, payload) — ordnat: väck/håll vaken först, sedan identitet.
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
    """Skicka payload i BÅDA header-formaten, returnera (format, svar) för det
    som ger något efter eko-strip."""
    for addressed in (False, True):
        frame = encode(payload, addr, TESTER_ADDRESS, addressed=addressed)
        raw = kl.converse(payload, addressed=addressed, overall=1.2)
        resp = strip_echo(raw, frame)
        if resp.strip(b"\x00"):
            return ("adr" if addressed else "oadr"), resp
        time.sleep(0.1)
    return None, b""


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x40
    t = SerialTransport(port, timeout=1.0)
    t.open()
    try:
        print(f"tyst 6 s, sedan slow init 0x{addr:02X}...")
        time.sleep(6)
        raw = t.slow_init(addr)
        kw = SerialTransport.parse_slow_init(raw)
        if not kw:
            print(f"  ingen session ({raw.hex(' ') or 'tyst'}) — avbryter")
            return 1
        print(f"  ✓ session: {raw.hex(' ')}  KW={kw[0]:#04x} {kw[1]:#04x}")
        kl = KLine(t, target=addr, source=TESTER_ADDRESS)
        for name, payload in REQUESTS:
            fmt, resp = try_request(kl, addr, payload)
            if resp:
                print(f"  {name:22s} [{fmt:4s}] → {resp.hex(' ')}   |{ascii_of(resp)}|")
            else:
                print(f"  {name:22s}        → (tyst)")
            time.sleep(0.15)
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
