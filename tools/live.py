"""Öppna en Td5-session och läs livedata (avkodat) ur kända identifiers.

    PYTHONPATH=src python3 tools/live.py /dev/ttyUSB0

Kör med tändning på men motorn AV (mindre brus på K-line).
"""
import sys
import time

from d2diag.kline import KLine, KLineTimeout
from d2diag.kwp2000 import KWP2000, NegativeResponse
from d2diag.td5 import LIDS, Td5, decode_lid, signals_for_lid
from d2diag.transport import SerialTransport


def open_session(kline: KLine, tries: int = 12) -> bool:
    for i in range(tries):
        try:
            sc = kline.fast_init()
        except KLineTimeout:
            print(f"  init {i + 1}: brus/timeout, försöker igen")
            continue
        if sc[:1] == b"\xc1":
            print(f"  init {i + 1}: C1 — färsk session, nyckelbytes {sc[1:].hex(' ')}")
            return True
        if sc[:1] == b"\x7f":
            # generalReject = sessionen är redan öppen (vi missade C1 i bruset).
            # Fortsätt — sessionen finns.
            print(f"  init {i + 1}: 7F — session redan öppen, kör vidare")
            return True
        print(f"  init {i + 1}: oväntat {sc.hex(' ') or 'tomt'}")
    return False


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    kline = KLine(SerialTransport(port, timeout=1.0))
    kwp = KWP2000(kline)
    td5 = Td5(kwp)
    with kline:
        if not open_session(kline):
            print("Kunde inte öppna session.")
            return 1
        print("session öppen (C1)")
        try:
            td5.start_session()
            print("StartDiagnosticSession 10 A0 OK")
        except NegativeResponse as exc:
            print(f"StartDiagnosticSession nekad: {exc}")
            return 1

        print("--- livedata ---")
        for lid in LIDS:
            try:
                data = kwp.read_local_identifier(lid)
            except NegativeResponse as exc:
                print(f"21 {lid:02X}: nekad (NRC 0x{exc.nrc:02X})")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"21 {lid:02X}: {type(exc).__name__}")
                continue
            vals = decode_lid(lid, data)
            print(f"21 {lid:02X}  raw={data.hex(' ')}")
            for sig in signals_for_lid(lid):
                if sig.name in vals:
                    print(f"    {sig.name:16} {vals[sig.name]:9.2f} {sig.unit}")
            try:
                kwp.tester_present()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
