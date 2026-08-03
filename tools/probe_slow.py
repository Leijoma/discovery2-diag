"""Bussavsökning med 5-baud slow init — leta moduler (SLABS m.fl.) på K-linen.

    PYTHONPATH=src python3 tools/probe_slow.py /dev/cu.usbserial-12345678 [lo] [hi]

Fast init nådde bara motorn (0x13). Övriga D2-moduler använder troligen 5-baud
slow init. Detta skickar slow init mot varje adress och rapporterar den som
svarar (ECU:n börjar med 0x55 sync-byte + keybytes). Stillastående, tändning på.
Varje adress tar ~2 s (5-baud-ramen är 10 bitar × 200 ms).
"""
import sys
import time

from d2diag.transport import SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x3F
    t = SerialTransport(port, timeout=1.0)
    t.open()
    hits = []
    try:
        print(f"slow-init-skanning 0x{lo:02X}–0x{hi:02X} (~{(hi-lo+1)*2.5:.0f} s)...")
        for addr in range(lo, hi + 1):
            try:
                resp = t.slow_init(addr)
            except Exception as exc:  # noqa: BLE001
                print(f"0x{addr:02X}: FEL {type(exc).__name__}: {exc}")
                break
            if resp:
                marker = "  <-- 0x55 SYNC!" if 0x55 in resp else ""
                print(f"0x{addr:02X}: {resp.hex(' ')}{marker}")
                hits.append((addr, resp))
            time.sleep(0.4)  # kort tystnad mellan adresser
    finally:
        t.close()
    print("\n--- sammanfattning ---")
    if hits:
        for addr, resp in hits:
            print(f"  0x{addr:02X}: {resp.hex(' ')}")
    else:
        print("  inga svar i intervallet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
