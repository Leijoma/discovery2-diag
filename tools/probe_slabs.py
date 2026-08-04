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

CANDIDATES = [
    ("motor 0x13 (kontroll)",         bytes.fromhex("8113f7810c")),
    ("SLABS? fast init 0x29 (F7)",    bytes.fromhex("8129f78122")),
    ("SLABS? funktionell 0x34 (F1)",  bytes.fromhex("c134f18167")),
]


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    kl = KLine(SerialTransport(port, timeout=1.0))
    with kl:
        print("håller linjen tyst 20 s...")
        time.sleep(20)
        for name, frame in CANDIDATES:
            kl._fast_init_pulse()          # 25 ms låg + 25 ms hög
            kl._flush_input()
            kl._t.send(frame)              # skicka rå kandidatram
            raw = kl._burst_read(0.06, 1.2)
            tag = "C1! (positivt)" if 0xC1 in raw else ("7F (svar-men-avvisat)" if 0x7F in raw else "")
            print(f"{name:32s} TX {frame.hex(' ')} → RX {raw.hex(' ') or 'tyst'}  {tag}")
            time.sleep(5)                  # ≥3–5 s mellan försök (K-line-ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
