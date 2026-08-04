"""Riktat fast-init-prov mot SLABS-kandidatadresser (KWP2000 fast init).

    PYTHONPATH=src python3 tools/probe_slabs.py /dev/cu.usbserial-12345678

Belägg (LR-forum + pyTD5Tester): Wabco SLABS på D2 initieras med **fast init**,
inte slow init. Konkreta kandidater ur pyTD5Tester/TD5Tester:
  - fysisk fast init mot 0x29, testare 0xF7:  81 29 F7 81 22
  - funktionell init mot 0x34, testare 0xF1:  C1 34 F1 81 67
Motorn (81 13 F7 81 0C) körs först som kontroll. Lång tystnad före, och ≥5 s
mellan försök (en slow-init-modul kan annars tolka låg-pulsen som 5-baud-start).
Stillastående, tändning på. Söker C1 (positivt) eller 7F (svar-men-avvisat).
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport

# Kandidaterna FÖRST (motorn hålls dormant → ingen öppen motorsession maskerar);
# motor-kontrollen SIST (den öppnar motorsessionen, men då är kandidaterna redan klara).
CANDIDATES = [
    ("SLABS? fast init 0x29 (F7)",    bytes.fromhex("8129f78122")),
    ("SLABS? funktionell 0x34 (F1)",  bytes.fromhex("c134f18167")),
    ("motor 0x13 (kontroll, SIST)",   bytes.fromhex("8113f7810c")),
]


def classify(raw: bytes, frame: bytes) -> "tuple[bytes, str]":
    """Plocka svaret EFTER vårt eko och klassificera (undvik falskt C1 i ekot)."""
    idx = raw.find(frame)
    resp = raw[idx + len(frame):] if idx >= 0 else raw
    if 0xC1 in resp:
        return resp, "C1! POSITIVT SVAR"
    if b"\x7f\x81" in resp:
        return resp, "7F 81 (generalReject — troligen motorn maskerar)"
    if 0x7F in resp:
        return resp, "7F"
    return resp, ("(inget svar)" if not resp.strip(b"\x00") else "brus/okänt")


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    kl = KLine(SerialTransport(port, timeout=1.0))
    with kl:
        for name, frame in CANDIDATES:
            print(f"håller linjen tyst 20 s (låt ev. session dö)...")
            time.sleep(20)
            kl._fast_init_pulse()          # 25 ms låg + 25 ms hög
            kl._flush_input()
            kl._t.send(frame)              # skicka rå kandidatram
            raw = kl._burst_read(0.06, 1.2)
            resp, tag = classify(raw, frame)
            print(f"{name:32s} TX {frame.hex(' ')} → svar {resp.hex(' ') or 'tyst'}  {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
