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

from d2diag.kline import KLine
from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        print("håller linjen tyst 20 s så motorsessionen (0x13) dör...")
        time.sleep(20)
        # Skippa 0x13: en öppen motorsession generalRejectar ALLA adresser och
        # maskerar övriga moduler. Genom att aldrig adressera 0x13 hålls motorn
        # dormant och bara andra moduler kan svara.
        for addr in [a for a in range(0x01, 0x40) if a != 0x13]:
            time.sleep(1.2)  # håll linjen tyst mellan försök
            kl = KLine(t, target=addr)
            kl._fast_init_pulse()
            raw = kl.converse(b"\x81", addressed=True)
            # eko = 81 <addr> f7 81 <cs> (5 bytes). Allt bortom det = ev. svar.
            has_c1 = 0xC1 in raw
            has_7f = 0x7F in raw
            extra = len(raw) > 6
            if has_c1 or has_7f or extra:
                tag = "C1!" if has_c1 else ("7F" if has_7f else "??")
                print(f"0x{addr:02X}: {tag}  {raw.hex(' ')}")
                hits.append((addr, tag))
    finally:
        t.close()
    print("\n--- sammanfattning ---")
    for addr, tag in hits:
        print(f"  0x{addr:02X}: {tag}")
    if not hits:
        print("  inga svar — SLABS m.fl. kräver troligen 5-baud slow init.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
