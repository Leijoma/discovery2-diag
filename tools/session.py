"""Öppna en Td5-diagnostiksession och läs identifiers — dumpar rå data.

    PYTHONPATH=src python3 tools/session.py /dev/ttyUSB0 [lid_hex ...]

fast init → StartDiagnosticSession (10 A0) → ReadDataByLocalIdentifier (21 xx).
Kör med tändning på men motorn AV.

Init:en är intermittent (brus/turnaround), så vi försöker om: brus → nytt försök;
7F (session redan öppen) → vänta ut timeouten och ta en färsk C1.
"""
import sys
import time

from d2diag.kline import KLine, KLineTimeout
from d2diag.kwp2000 import KWP2000, KWP2000Error, NegativeResponse
from d2diag.transport import SerialTransport

DEFAULT_LIDS = [0x09, 0x1A, 0x1B, 0x40, 0x10, 0x11, 0x15, 0x20, 0x21, 0x22]


def open_session(kline: KLine, tries: int = 8) -> "bytes | None":
    """Kör fast init tills vi får ett positivt StartCommunication (C1)."""
    for i in range(tries):
        try:
            sc = kline.fast_init()
        except KLineTimeout:
            print(f"  init-försök {i + 1}: brus/timeout, försöker igen")
            continue
        if sc[:1] == b"\xc1":
            return sc
        if sc[:1] == b"\x7f":
            print(f"  init-försök {i + 1}: 7F (session redan öppen) — väntar ut timeout")
            time.sleep(6)
            continue
        print(f"  init-försök {i + 1}: oväntat svar {sc.hex(' ')}")
    return None


def main() -> int:
    args = sys.argv[1:]
    port = args[0] if args else "/dev/ttyUSB0"
    lids = [int(x, 16) for x in args[1:]] or DEFAULT_LIDS

    kline = KLine(SerialTransport(port, timeout=1.0))
    kwp = KWP2000(kline)
    with kline:
        sc = open_session(kline)
        if sc is None:
            print("Kunde inte öppna session efter flera försök.")
            return 1
        print(f"fast init OK: {sc.hex(' ')}  (nyckelbytes {sc[1:].hex(' ')})")

        try:
            sess = kwp.start_diagnostic_session(0xA0)
            print(f"StartDiagnosticSession 10 A0 → 50 {sess.hex(' ')}")
        except (NegativeResponse, KWP2000Error) as exc:
            print(f"StartDiagnosticSession nekad: {exc}")
            return 1

        print("--- identifiers (21 xx) ---")
        for lid in lids:
            try:
                data = kwp.read_local_identifier(lid)
                print(f"  21 {lid:02X} → {data.hex(' ')}  ({len(data)} bytes)")
            except NegativeResponse as exc:
                print(f"  21 {lid:02X} → nekad (NRC 0x{exc.nrc:02X})")
            except Exception as exc:  # noqa: BLE001
                print(f"  21 {lid:02X} → {type(exc).__name__}: {exc}")
            try:
                kwp.tester_present()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
