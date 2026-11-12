#!/usr/bin/env python3
"""SLABS hold from the Mac: keep ONE SLABS session through a drive and log the fault onset ORDER.

The test and its decision rule are in references/test_plan.md T-23. The loop itself is
d2diag.slabs.hold (unit-tested). This script adds the serial port, a 1 Hz pace, a CSV and lamp
marks.

    PYTHONPATH=src python3 tools/slabs_hold.py auto                  # KKL cable
    PYTHONPATH=src python3 tools/slabs_hold.py /dev/cu.usbserial-XXXX --esp   # ESP node over USB

Start it at a STANDSTILL right after an ignition cycle (SLABS won't accept a new connection once
the car has moved). With a KKL cable the ESP node must be muted or unplugged, because two masters
on the same K-line collide. With --esp the node goes into cable mode on its own and stops polling.

While it runs, press Enter when the amigos light. Type e.g. "4 braking" first to note how many
lamps and what you were doing. Ctrl-C ends it and releases the link (82).
"""
from __future__ import annotations

import argparse
import csv
import os
import queue
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.kline import KLine  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.slabs import SLABS_ADDRESS, Slabs  # noqa: E402
from d2diag.slabs.hold import HoldEvent, SlabsHold  # noqa: E402
from d2diag.transport import EspTransport, SerialTransport  # noqa: E402

STEP_S = 1.0       # one request per second: the SLABS load budget (slabs_protocol.md)
RETRY_S = 20.0     # after a lost session / failed init, try again this often (fails while moving)
FIELDS = list(HoldEvent.__dataclass_fields__) + ["local"]


def _local(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3]


def _show(e: HoldEvent) -> None:
    ts = _local(e.t)
    if e.kind == "edge":
        what = "ON " if e.state else "off"
        tag = "  (already set at connect)" if e.base else ""
        print(f"{ts}  #{e.seq:<5} {e.block.upper():3} {what} {e.bit:5} {e.text}{tag}")
    elif e.kind == "status":
        print(f"{ts}  #{e.seq:<5} held {e.up_s:7.0f} s   wheels {e.raw}")
    elif e.kind == "up":
        print(f"{ts}  SLABS session UP. Drive when ready; Enter = lamps lit")
    elif e.kind == "down":
        print(f"{ts}  SLABS session LOST after {e.up_s:.0f} s ({e.text})")
    elif e.kind == "estab_fail":
        print(f"{ts}  SLABS did not answer ({e.text}); retrying in {RETRY_S:.0f} s")
    elif e.kind == "mark":
        print(f"{ts}  ** MARK: {e.text or 'lamps lit'}")


def _stdin_marks(q: "queue.Queue[str]") -> None:
    for line in sys.stdin:
        q.put(line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="SLABS hold: log SLABS fault onset order (T-23)")
    ap.add_argument("port", help="serial device, or 'auto' to detect the KKL cable")
    ap.add_argument("--esp", action="store_true", help="talk through the ESP node over USB")
    ap.add_argument("--csv", help="output CSV (default logs/slabs_hold-<time>.csv)")
    args = ap.parse_args()

    port = args.port
    if not args.esp:
        from d2diag.ports import resolve_serial_port
        port = resolve_serial_port(args.port)
    transport = EspTransport(port) if args.esp else SerialTransport(port, timeout=1.0)
    slabs = Slabs(KWP2000(KLine(transport, target=SLABS_ADDRESS), tolerant=True))
    hold = SlabsHold(slabs, establish=lambda: slabs.establish(progress=lambda m: print(f"  … {m}")))

    out = args.csv or os.path.join("logs", f"slabs_hold-{datetime.now():%Y%m%d-%H%M%S}.csv")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    marks: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_stdin_marks, args=(marks,), daemon=True).start()
    print(f"SLABS hold on {port}{' (ESP)' if args.esp else ''} → {out}")

    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()

        def emit(events: "list[HoldEvent]") -> None:
            for e in events:
                _show(e)
                w.writerow({**asdict(e), "local": _local(e.t)})
            if events:
                fh.flush()   # an unplugged cable or a dead laptop must not lose the order

        slabs.open()
        try:
            next_try = 0.0
            while True:
                while not marks.empty():
                    emit([HoldEvent(time.time(), "mark", seq=hold.seq,
                                    up_s=round(hold.up_s(), 1), text=marks.get())])
                if not hold.up:
                    if time.monotonic() >= next_try:
                        emit(hold.connect())
                        next_try = time.monotonic() + RETRY_S
                    time.sleep(0.2)
                    continue
                t0 = time.monotonic()
                emit(hold.step())
                time.sleep(max(0.0, STEP_S - (time.monotonic() - t0)))
        except KeyboardInterrupt:
            print("\nstopping")
        finally:
            slabs.release()    # 82 + close: never leave the link open on the shared bus
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
