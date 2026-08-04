"""Starta realtidsdashboarden.

    # mock-data (ingen bil) — för UI-utveckling / förhandsvisning:
    PYTHONPATH=src python3 tools/dashboard.py --mock

    # riktig Td5 mot bilen:
    PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-12345678

Öppna sedan http://localhost:8080 (eller Pi:ns adress i bilen från mobilen).
"""
import argparse
import os
import sys

# Gör verktyget körbart som "python3 tools/dashboard.py" utan PYTHONPATH=src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.web import MockDataSource, Td5DataSource  # noqa: E402
from d2diag.web.server import DiagServer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery 2 realtidsdashboard")
    ap.add_argument("--serial", help="serieport för riktig Td5 (utelämna → mock)")
    ap.add_argument("--mock", action="store_true", help="tvinga mock-data")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080, help="HTTP-port (default 8080)")
    ap.add_argument("--interval", type=float, default=0.5, help="poll-/strömintervall (s)")
    ap.add_argument("--log-file", help="logga data till denna JSONL-fil")
    ap.add_argument("--log-dir", help="logga till DIR/session-<tid>.jsonl (auto-namn)")
    ap.add_argument("--log-interval", type=float, default=2.0,
                    help="min sekunder mellan loggrader (feländring loggas alltid)")
    args = ap.parse_args()

    if args.serial and not args.mock:
        source = Td5DataSource(args.serial)
    else:
        source = MockDataSource()

    logger = None
    log_path = args.log_file
    if not log_path and args.log_dir:
        import datetime as _dt
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(args.log_dir, f"session-{stamp}.jsonl")
    if log_path:
        from d2diag.web.logger import SnapshotLogger
        logger = SnapshotLogger(log_path, min_interval=args.log_interval)

    srv = DiagServer(
        source, host=args.host, port=args.port,
        poll_interval=args.interval, stream_interval=args.interval, logger=logger,
    )
    print(f"Dashboard: http://localhost:{args.port}   (källa: {source.name})")
    if log_path:
        print(f"Loggar data → {log_path}")
    print("Ctrl-C för att avsluta.")
    try:
        srv.serve()
    except KeyboardInterrupt:
        srv.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
