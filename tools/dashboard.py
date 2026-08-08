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

from d2diag.web import (  # noqa: E402
    MockDataSource,
    MockSlabsDataSource,
    SlabsDataSource,
    Td5DataSource,
)
from d2diag.web.server import DiagServer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery 2 realtidsdashboard")
    ap.add_argument("--serial", help="serieport för riktig Td5 (utelämna → mock)")
    ap.add_argument("--mock", action="store_true", help="tvinga mock-data")
    ap.add_argument("--slabs", action="store_true",
                    help="SLABS-källa istället för Td5 (fast init 0x29; kräver sändande kabel)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080, help="HTTP-port (default 8080)")
    ap.add_argument("--interval", type=float, default=0.5, help="poll-/strömintervall (s)")
    ap.add_argument("--log-file", help="logga data till denna JSONL-fil")
    ap.add_argument("--log-dir", help="logga till DIR/session-<tid>.jsonl (auto-namn)")
    ap.add_argument("--log-interval", type=float, default=2.0,
                    help="min sekunder mellan loggrader (feländring loggas alltid)")
    ap.add_argument("--dict", dest="dict_path",
                    help="sökväg till felkodsordboken (default: syskon-repot 'Discovery 2/')")
    ap.add_argument("--docs", action="append", default=[],
                    help="extra katalog med .md att visa i Dokument-fliken (kan upprepas)")
    args = ap.parse_args()

    live = args.serial and not args.mock
    # Multi-modul: både motor och SLABS finns, men bara EN är aktiv (K-line = delad
    # buss). Flikvalet i UI:t byter aktiv modul (etablerar session vid val).
    if live:
        modules = {"motor": Td5DataSource(args.serial), "slabs": SlabsDataSource(args.serial)}
    else:
        modules = {"motor": MockDataSource(), "slabs": MockSlabsDataSource()}
    active = "slabs" if args.slabs else "motor"

    logger = None
    log_path = args.log_file
    if not log_path and args.log_dir:
        import datetime as _dt
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(args.log_dir, f"session-{stamp}.jsonl")
    if log_path:
        from d2diag.web.logger import SnapshotLogger
        logger = SnapshotLogger(log_path, min_interval=args.log_interval)

    from d2diag.menus import MENUS  # modul-menyregister för Karta-fliken
    from d2diag.web.docs import DocLibrary  # markdown-vy för Dokument-fliken

    # Dokument-fliken speglar de KANONISKA källfilerna (ingen kopia):
    #   Facit = felkodsordboken i register-repot (syskonmapp 'Discovery 2/')
    #   Referens = diag-repots references/*.md
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dict_path = args.dict_path or os.path.join(
        os.path.dirname(repo_root), "Discovery 2", "discovery2_reference tool_fault_dictionary.md")
    docs = DocLibrary()
    docs.add_file(dict_path, title="reference tool felkodsordbok (facit)", group="Facit")
    docs.add_dir(os.path.join(repo_root, "references"), group="Referens")
    for extra in args.docs:
        docs.add_dir(extra, group="Extra")

    srv = DiagServer(
        modules, host=args.host, port=args.port,
        poll_interval=args.interval, stream_interval=args.interval, logger=logger,
        active=active, menus=MENUS, docs=docs,
    )
    print(f"Dokument: {len(docs.index())} st i Dokument-fliken")
    print(f"Dashboard: http://localhost:{args.port}   (moduler: {', '.join(modules)} · aktiv: {active})")
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
