"""Flexibel modul-skanning — prova olika init-varianter mot ett adressintervall.

    PYTHONPATH=src python3 tools/probe_scan.py PORT MODE [lo] [hi]

MODE:
    fast-f7   fysisk fast init, testare 0xF7   (81 <addr> F7 81)
    fast-f1   fysisk fast init, testare 0xF1   (81 <addr> F1 81)
    func-f1   funktionell fast init, F1        (C1 <addr> F1 81)
    func-f7   funktionell fast init, F7        (C1 <addr> F7 81)
    slow      5-baud slow init (8N1)           → letar 0x55-sync

Motorn (0x13) hoppas över (dess öppna session generalRejectar allt och maskerar
bussen). Lång tystnad först + gap mellan. Söker C1/7F (fast/func) eller 0x55 (slow)
EFTER vårt eko. Stillastående, tändning på. Kör en MODE i taget.

Rekommenderad ordning nästa biltest: fast-f1 → func-f1 → func-f7 → slow.
(fast-f7 0x01–0xFF är redan negativ.)
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport


def build_frame(mode: str, addr: int) -> "bytes | None":
    """Rå init-ram (inkl. checksumma) för läget, eller None för slow."""
    if mode == "slow":
        return None
    tester = 0xF1 if mode.endswith("f1") else 0xF7
    fmt = 0xC1 if mode.startswith("func") else 0x81   # funktionell vs fysisk
    b = bytes([fmt, addr, tester, 0x81])
    return b + bytes([sum(b) & 0xFF])


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    mode = sys.argv[2] if len(sys.argv) > 2 else "fast-f1"
    lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x01
    hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0xFF
    if mode not in ("fast-f7", "fast-f1", "func-f7", "func-f1", "slow"):
        print(f"okänt MODE: {mode}")
        return 2

    t = SerialTransport(port, timeout=1.0)
    t.open()
    kl = KLine(t)
    per = 2.6 if mode == "slow" else 1.1
    hits = []
    try:
        print(f"skannar {mode} 0x{lo:02X}–0x{hi:02X} (~{(hi-lo+1)*per:.0f} s). Tyst 20 s först...")
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
                print(f"0x{addr:02X}: C1! POSITIVT  {resp.hex(' ')}")
                hits.append((addr, "C1"))
            elif 0x7F in resp:
                print(f"0x{addr:02X}: 7F  {resp.hex(' ')}")
                hits.append((addr, "7F"))
    finally:
        t.close()
    print("\n--- träffar ---")
    print("  " + (", ".join(f"0x{a:02X}={tag}" for a, tag in hits) if hits else "inga"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
