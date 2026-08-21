"""Open a Td5 session and read live data (decoded) from known identifiers.

    PYTHONPATH=src python3 tools/live.py /dev/ttyUSB0

Run with ignition on but the engine OFF (less noise on the K-line).
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
            print(f"  init {i + 1}: noise/timeout, retrying")
            continue
        if sc[:1] == b"\xc1":
            print(f"  init {i + 1}: C1 — fresh session, key bytes {sc[1:].hex(' ')}")
            return True
        if sc[:1] == b"\x7f":
            # generalReject = the session is already open (we missed C1 in the noise).
            # Continue — the session exists.
            print(f"  init {i + 1}: 7F — session already open, continuing")
            return True
        print(f"  init {i + 1}: unexpected {sc.hex(' ') or 'empty'}")
    return False


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    kline = KLine(SerialTransport(port, timeout=1.0))
    kwp = KWP2000(kline)
    td5 = Td5(kwp)
    with kline:
        if not open_session(kline):
            print("Could not open session.")
            return 1
        print("session open (C1)")
        try:
            td5.start_session()
            print("StartDiagnosticSession 10 A0 OK")
        except NegativeResponse as exc:
            print(f"StartDiagnosticSession denied: {exc}")
            return 1

        print("--- live data ---")
        for lid in LIDS:
            try:
                data = kwp.read_local_identifier(lid)
            except NegativeResponse as exc:
                print(f"21 {lid:02X}: denied (NRC 0x{exc.nrc:02X})")
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
