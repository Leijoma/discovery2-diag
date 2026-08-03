"""Starta realtidsdashboarden.

    # mock-data (ingen bil) — för UI-utveckling / förhandsvisning:
    PYTHONPATH=src python3 tools/dashboard.py --mock

    # riktig Td5 mot bilen:
    PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-12345678

Öppna sedan http://localhost:8080 (eller Pi:ns adress i bilen från mobilen).
"""
import argparse

from d2diag.web import MockDataSource, Td5DataSource
from d2diag.web.server import DiagServer


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery 2 realtidsdashboard")
    ap.add_argument("--serial", help="serieport för riktig Td5 (utelämna → mock)")
    ap.add_argument("--mock", action="store_true", help="tvinga mock-data")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080, help="HTTP-port (default 8080)")
    ap.add_argument("--interval", type=float, default=0.5, help="poll-/strömintervall (s)")
    args = ap.parse_args()

    if args.serial and not args.mock:
        source = Td5DataSource(args.serial)
    else:
        source = MockDataSource()

    srv = DiagServer(
        source, host=args.host, port=args.port,
        poll_interval=args.interval, stream_interval=args.interval,
    )
    print(f"Dashboard: http://localhost:{args.port}   (källa: {source.name})")
    print("Ctrl-C för att avsluta.")
    try:
        srv.serve()
    except KeyboardInterrupt:
        srv.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
