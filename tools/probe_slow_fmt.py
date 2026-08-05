"""Hitta rätt post-slow-init header-format — prova konkreta råramar mot en modul.

    PYTHONPATH=src python3 tools/probe_slow_fmt.py PORT ADDR_HEX

För varje kandidatram: gör 5-baud slow init (egen session), skicka råramen, dumpa
HELA bursten (även skräp). Ett svar med 0x7E (TesterPresent-ACK) eller 0x7F (neg)
avslöjar rätt format. ≥8 s mellan (session-lås). Stillastående, tändning på.
"""
import sys
import time

from d2diag.kline import KLine
from d2diag.transport import SerialTransport


def cs(b: bytes) -> bytes:
    return b + bytes([sum(b) & 0xFF])


def candidates(addr: int):
    a = addr
    # TesterPresent (0x3E) i olika KWP2000/ISO-format + testaradresser
    return [
        ("oadr len-i-fmt         ", cs(bytes([0x01, 0x3E]))),
        ("adr fmt=0x81 F7        ", cs(bytes([0x81, a, 0xF7, 0x3E]))),
        ("adr fmt=0x81 F1        ", cs(bytes([0x81, a, 0xF1, 0x3E]))),
        ("funktionell C1 F1      ", cs(bytes([0xC1, a, 0xF1, 0x3E]))),
        ("adr+längdbyte 80..01   ", cs(bytes([0x80, a, 0xF7, 0x01, 0x3E]))),
        ("adr+längdbyte 80 F1    ", cs(bytes([0x80, a, 0xF1, 0x01, 0x3E]))),
        ("ISO9141 68 6A F1       ", cs(bytes([0x68, 0x6A, 0xF1, 0x3E]))),
        ("ISO9141 68 addr F1     ", cs(bytes([0x68, a, 0xF1, 0x3E]))),
        ("ISO9141 82 addr F1     ", cs(bytes([0x82, a, 0xF1, 0x3E]))),
        ("adr src=0x03           ", cs(bytes([0x81, a, 0x03, 0x3E]))),
    ]


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x40
    t = SerialTransport(port, timeout=1.0)
    t.open()
    kl = KLine(t, target=addr)
    hits = []
    try:
        print(f"tyst 6 s först...")
        time.sleep(6)
        for name, frame in candidates(addr):
            raw_init = t.slow_init(addr)
            if not (raw_init and raw_init[0] == 0x55):
                print(f"  {name} init-tyst, hoppar")
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
                mark = "  <<< 7F neg (svar!)"
                hits.append((name, "7F"))
            print(f"  {name} TX {frame.hex(' ')} → {resp.hex(' ') or 'tyst'}{mark}")
            time.sleep(8)
    finally:
        t.close()
    print("\n--- format-träffar ---")
    print("  " + (", ".join(f"{n.strip()}={tag}" for n, tag in hits) if hits else "inga"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
