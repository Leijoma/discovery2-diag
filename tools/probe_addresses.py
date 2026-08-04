"""Bussavsökning: prova fast init mot alla K-line-adresser, rapportera svar.

    PYTHONPATH=src python3 tools/probe_addresses.py /dev/cu.usbserial-12345678

På D2 delar flera styrdon K-linen (pin 7). Motorn = 0x13. Detta letar efter andra
moduler (t.ex. SLABS) som svarar på fast init. Rapporterar bara adresser vars
burst innehåller ett riktigt svar (C1 = positivt, 7F = avvisat-men-närvarande).
Stillastående, tändning på. (SLABS kan kräva 5-baud slow init i stället — då syns
inget här, vilket också är ett svar.)
"""
import sys
import time

from d2diag.kline import TESTER_ADDRESS, KLine, encode
from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x3F
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        print(f"skannar 0x{lo:02X}–0x{hi:02X} (fysisk fast init, motorn dormant, ~{(hi-lo+1)*1.4:.0f} s)")
        print("håller linjen tyst 20 s först...")
        time.sleep(20)
        # Skippa 0x13: en öppen motorsession generalRejectar ALLA adresser och
        # maskerar övriga moduler. Adressera aldrig 0x13 → motorn hålls dormant.
        for addr in [a for a in range(lo, hi + 1) if a != 0x13]:
            time.sleep(1.0)
            kl = KLine(t, target=addr)
            kl._fast_init_pulse()
            raw = kl.converse(b"\x81", addressed=True)
            # strippa vårt eko (81 addr F7 81 cs) → titta bara på svaret efter
            echo = encode(b"\x81", target=addr, source=TESTER_ADDRESS, addressed=True)
            idx = raw.find(echo)
            resp = raw[idx + len(echo):] if idx >= 0 else raw
            if 0xC1 in resp or 0x7F in resp or resp.strip(b"\x00"):
                tag = "C1! POSITIVT" if 0xC1 in resp else ("7F" if 0x7F in resp else "brus/okänt")
                print(f"0x{addr:02X}: {tag}  svar={resp.hex(' ')}")
                hits.append((addr, tag))
    finally:
        t.close()
    print("\n--- sammanfattning ---")
    for addr, tag in hits:
        print(f"  0x{addr:02X}: {tag}")
    if not hits:
        print("  inga svar i intervallet — prova annan MODE (probe_scan.py: fast-f1/func/slow).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
