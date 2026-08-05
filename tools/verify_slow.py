"""Verifiera slow-init-träffarna — upprepa + tolka handskakningen byte för byte.

    PYTHONPATH=src python3 tools/verify_slow.py PORT [addr_hex ...]

Ett ÄKTA ISO 9141 / ISO 14230 5-baud-svar: ``0x55`` sync + KW1 + KW2, och sedan
(efter att vi skickat ``~KW2``) ECU:ns ``~address``-bekräftelse. Om ``~address``
finns i svansen är handskakningen KOMPLETT = riktig modul, inte artefakt.
Upprepar varje adress 3× för att bevisa konsistens. Stillastående, tändning på.
Default-adresser = träffarna 0x18/0x33/0x40.
"""
import sys
import time

from d2diag.transport import SerialTransport


def interpret(addr: int, raw: bytes) -> str:
    if not raw or raw[0] != 0x55:
        return "ingen sync → tyst/artefakt"
    if len(raw) < 3:
        return "sync men för kort (ingen KW)"
    kw1, kw2 = raw[1], raw[2]
    inv = (~addr) & 0xFF
    complete = inv in raw[3:]
    tag = "KOMPLETT ✓ äkta modul" if complete else f"OFULLSTÄNDIG (~addr {inv:#04x} saknas)"
    return f"KW={kw1:#04x} {kw2:#04x}  {tag}"


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    gap = 8.0  # ≥ sessions-timeout så modulen hinner släppa och svarar på nästa init
    addrs = [int(a, 16) for a in sys.argv[2:]] or [0x18, 0x33, 0x40]
    t = SerialTransport(port, timeout=1.0)
    t.open()
    results = {}
    try:
        print("tyst 5 s först...")
        time.sleep(5)
        for addr in addrs:
            print(f"\n== 0x{addr:02X} (~addr {(~addr)&0xFF:#04x}) ==")
            oks = 0
            for i in range(3):
                raw = t.slow_init(addr)
                txt = interpret(addr, raw)
                if "KOMPLETT" in txt:
                    oks += 1
                print(f"  #{i+1}: {(raw.hex(' ') or 'tyst'):18s} {txt}")
                time.sleep(gap)
            results[addr] = oks
    finally:
        t.close()
    print("\n--- VERDIKT (kompletta av 3) ---")
    for addr, oks in results.items():
        verdict = "ÄKTA MODUL" if oks >= 2 else ("flakig/osäker" if oks == 1 else "artefakt/tyst")
        print(f"  0x{addr:02X}: {oks}/3 kompletta → {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
