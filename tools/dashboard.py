"""Start the realtime dashboard.

    # mock data (no car) — for UI development / preview:
    PYTHONPATH=src python3 tools/dashboard.py --mock

    # real Td5 against the car:
    PYTHONPATH=src python3 tools/dashboard.py --serial /dev/cu.usbserial-12345678

Then open http://localhost:8080 (or the Pi's address in the car from your phone).
"""
import argparse
import os
import sys

# Make the tool runnable as "python3 tools/dashboard.py" without PYTHONPATH=src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.web import (  # noqa: E402
    MockDataSource,
    MockSlabsDataSource,
    SlabsDataSource,
    Td5DataSource,
)
from d2diag.web.server import DiagServer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery 2 realtime dashboard")
    ap.add_argument("--serial", help="serial port for a real Td5 (omit → mock)")
    ap.add_argument("--mock", action="store_true", help="force mock data")
    ap.add_argument("--slabs", action="store_true",
                    help="SLABS source instead of Td5 (fast init 0x29; requires a transmitting cable)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port (default 8080)")
    ap.add_argument("--interval", type=float, default=0.5, help="poll/stream interval (s)")
    ap.add_argument("--log-file", help="log data to this JSONL file")
    ap.add_argument("--log-dir", help="log to DIR/session-<time>.jsonl (auto-named)")
    ap.add_argument("--log-interval", type=float, default=2.0,
                    help="min seconds between log rows (a fault change is always logged)")
    ap.add_argument("--csv", action="store_true",
                    help="start CSV live-data logging immediately (logs/livedata-<time>.csv)")
    ap.add_argument("--public", action="store_true",
                    help="public/simple UI: home page + TD5/SLABS/Faults only "
                         "(hide Map/Capture/Docs + actuators)")
    ap.add_argument("--fault-watch", action="store_true",
                    help="poll fault codes every cycle (~0.5s) to catch intermittent faults")
    ap.add_argument("--admin-password", default=os.environ.get("D2DIAG_ADMIN_PW"),
                    help="password for the /admin mapping console (Basic Auth). "
                         "Also read from D2DIAG_ADMIN_PW. Unset → admin is ungated "
                         "(fine on localhost, NOT on a public bind).")
    ap.add_argument("--dict", dest="dict_path",
                    help="path to the fault-code dictionary (default: sibling repo 'Discovery 2/')")
    ap.add_argument("--docs", action="append", default=[],
                    help="extra directory of .md files to show in the Docs tab (repeatable)")
    ap.add_argument("--sniff", metavar="PORT",
                    help="ESP32 sniff port for the Map tab (passive RX-only; reference tool polls)")
    ap.add_argument("--replay", metavar="FILE",
                    help="replay a sniff log in the Map tab (for testing without a vehicle)")
    ap.add_argument("--raw-log", action="store_true",
                    help="log ALL raw TX/RX to logs/raw-<module>-<time>.log (for mapping). "
                         "Appends across reconnects; one file per module per run.")
    ap.add_argument("--allow-shutdown", action="store_true",
                    help="expose a 'Shut down Pi' button in Settings (set on the Pi's "
                         "systemd unit; needs passwordless sudo for shutdown)")
    args = ap.parse_args()

    # Raw bus log (TX/RX) for mapping — off by default, on with --raw-log.
    _repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_log_dir = os.path.join(_repo, "logs") if args.raw_log else None
    # The fuel computer's lifetime total is persisted here (survives restart). Gitignored.
    fuel_state_path = os.path.join(_repo, "fuel_totals.json")

    # Both mock and live variants are built for each module; the mode (mock/live) is
    # chosen in the UI and can be switched at runtime. Live sources autodetect the port
    # (``auto``) if none is given → fail softly at poll time if the cable is missing. The
    # flags only set the START mode. Multi-module: only ONE module active at a time
    # (K-line = shared bus).
    port = args.serial or "auto"
    variants = {
        "motor": {"mock": MockDataSource(),
                  "live": Td5DataSource(port, raw_log_dir=raw_log_dir, fuel_state_path=fuel_state_path)},
        "slabs": {"mock": MockSlabsDataSource(), "live": SlabsDataSource(port, raw_log_dir=raw_log_dir)},
    }
    # Public build is LIVE-only (a real user plugs in the cable). --mock forces mock
    # (dev/preview). Otherwise --serial or --public → live, else mock.
    if args.mock:
        mode = "mock"
    elif args.serial or args.public:
        mode = "live"
    else:
        mode = "mock"
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

    from d2diag.menus import MENUS  # module menu registry for the Map tab
    from d2diag.web.docs import DocLibrary  # markdown view for the Docs tab

    # The Docs tab mirrors the CANONICAL source files (not a copy):
    #   Answer key = the fault-code dictionary in the register repo (sibling folder 'Discovery 2/')
    #   Reference = the diag repo's references/*.md
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dict_path = args.dict_path or os.path.join(
        os.path.dirname(repo_root), "Discovery 2", "discovery2_reference tool_fault_dictionary.md")
    docs = DocLibrary()
    docs.add_file(dict_path, title="reference tool fault-code dictionary (answer key)", group="Answer key")
    docs.add_dir(os.path.join(repo_root, "references"), group="Reference")
    for extra in args.docs:
        docs.add_dir(extra, group="Extra")

    # Map tab: passive sniff feed (live ESP32 or replayed log).
    sniffer = None
    if args.sniff:
        from d2diag.web.sniffer import SnifferFeed
        sniffer = SnifferFeed.from_serial(args.sniff)
        print(f"Sniff (live): {args.sniff} → Map tab")
    elif args.replay:
        from d2diag.web.sniffer import SnifferFeed
        # looping replay so the freshness badge shows "LIVE" in the preview
        sniffer = SnifferFeed.from_file(args.replay, delay=0.008, loop=True)
        print(f"Sniff (replay): {args.replay} → Map tab (freshness demo)")

    # Labeled live captures (Capture tab) → durable JSONL dataset.
    captures_path = os.path.join(repo_root, "logs", "labeled_captures.jsonl")
    os.makedirs(os.path.dirname(captures_path), exist_ok=True)

    csv_dir = os.path.join(repo_root, "logs")
    from d2diag.community import Community  # opt-in community sharing (default OFF)
    community = Community()
    srv = DiagServer(
        host=args.host, port=args.port,
        poll_interval=args.interval, stream_interval=args.interval, logger=logger,
        active=active, menus=MENUS, docs=docs, sniffer=sniffer, captures_path=captures_path,
        variants=variants, mode=mode, scan_port=port, csv_dir=csv_dir, community=community,
        public=args.public, fault_watch=args.fault_watch,
        admin_password=args.admin_password,
        allow_shutdown=args.allow_shutdown,
    )
    if raw_log_dir:
        print(f"Raw TX/RX log → {raw_log_dir}/raw-<module>-<time>.log")
    if args.admin_password:
        print("Admin: /admin (mapping console) — password protected")
    elif args.host not in ("127.0.0.1", "localhost"):
        print("Admin: /admin OPEN (no --admin-password) — set one for a public bind")
    print(f"Docs: {len(docs.index())} in the Docs tab")
    print(f"Captures → {captures_path}")
    print(f"Dashboard: http://localhost:{args.port}   (modules: {', '.join(variants)} · active: {active} · mode: {mode})")
    print(f"Live port: {port}  (switch mock/live in the UI)")
    if log_path:
        print(f"Logging data → {log_path}")
    if args.csv:
        print(f"CSV live log → {srv.start_csv().get('path')}")
    print("Ctrl-C to quit.")
    try:
        srv.serve()
    except KeyboardInterrupt:
        srv.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
