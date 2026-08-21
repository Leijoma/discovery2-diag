#!/usr/bin/env python3
"""LID sweep for Td5 — **read-only** hunt for dynamic fields (e.g. the real MAF).

Reads raw bytes for a list of LIDs at a high rate, decodes every u16 at even
offsets, and prints live + a JSONL log. On exit it summarizes the **span**
(min→max) per LID/offset. A field that varies a lot when you blip the throttle is
an air-mass/load candidate; one that sits still is a constant/status.

Background: ``maf_raw`` (1C@4) turned out NOT to be air mass (car test 2026-08-20:
57 at ignition-on, 0 while the engine runs). The real MAF LID is unmapped. The MAF's
signature is ≈0 with the engine off, rises with rpm, and jumps immediately on throttle —
run the sweep at idle and blip the throttle so it shows up in the span summary.

Service ``21`` (ReadDataByLocalIdentifier) only — no writes.

    PYTHONPATH=src python3 tools/lid_sweep.py --serial auto
    PYTHONPATH=src python3 tools/lid_sweep.py --lids 1C,1B,1A,1D,1E --hz 4 --seconds 40
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.kline import KLine  # noqa: E402
from d2diag.kline.kline import KLineError  # noqa: E402
from d2diag.kwp2000 import KWP2000  # noqa: E402
from d2diag.kwp2000.kwp2000 import KWP2000Error  # noqa: E402
from d2diag.td5 import Td5  # noqa: E402
from d2diag.transport import SerialTransport  # noqa: E402
from d2diag.web.sources import resolve_serial_port  # noqa: E402

# Default: RPM (09) as the correlation reference + the "air/fuel" quarter where the
# MAF plausibly lives, plus a few neighbors. The MAF must FOLLOW the rpm → 09 must be included.
_DEFAULT_LIDS = "09,1C,1B,1A,1D,1E,1F,20"
_RPM_KEY = "09@0"   # 21 09 u16 = rpm; the reference to correlate against


def _u16s(raw: bytes) -> "list[int]":
    """All u16 (big-endian) at even offsets — so every 2-byte field shows up."""
    return [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw) - 1, 2)]


def _pearson(xs: "list[float]", ys: "list[float]") -> "float | None":
    """Pearson correlation without numpy. None if too few/constant values."""
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="auto")
    ap.add_argument("--lids", default=_DEFAULT_LIDS,
                    help=f"comma-separated LIDs in hex (default {_DEFAULT_LIDS})")
    ap.add_argument("--hz", type=float, default=4.0, help="reads per second (default 4)")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after N s (0 = until Ctrl-C)")
    args = ap.parse_args()

    lids = [int(x, 16) for x in args.lids.replace(" ", "").split(",") if x]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs("logs", exist_ok=True)
    out_path = f"logs/lid_sweep-{stamp}.jsonl"

    try:
        port = resolve_serial_port(args.serial)
    except FileNotFoundError as exc:
        print(f"no cable: {exc}")
        return 1

    t = Td5(KWP2000(KLine(SerialTransport(port, timeout=1.0)), tolerant=True))
    t.open()
    span: "dict[str, list[int]]" = {}   # "1C@2" -> [min, max]
    samples: "list[dict]" = []          # per cycle: {key: value} for correlation
    fh = open(out_path, "w", encoding="utf-8")
    period = 1.0 / max(0.1, args.hz)
    n = 0
    try:
        print(f"LID sweep {stamp} — establishing Td5 session …")
        t.establish(progress=lambda m: print(f"  {m}"))
        print(f"✓ connected. Logging → {out_path}")
        print("  Blip the throttle while it's rolling; Ctrl-C for the summary.\n")
        t0 = time.perf_counter()
        while True:
            row: "dict[str, str]" = {}
            cells = []
            cyc: "dict[str, int]" = {}
            for lid in lids:
                try:
                    raw = t.read_local(lid)
                except (KLineError, KWP2000Error) as exc:
                    row[f"{lid:02X}"] = f"ERR:{type(exc).__name__}"
                    cells.append(f"{lid:02X}=--")
                    continue
                row[f"{lid:02X}"] = raw.hex(" ")
                vals = _u16s(raw)
                cells.append(f"{lid:02X}[" + " ".join(str(v) for v in vals) + "]")
                for off, v in enumerate(vals):
                    key = f"{lid:02X}@{off*2}"
                    cyc[key] = v
                    lo, hi = span.get(key, [v, v])
                    span[key] = [min(lo, v), max(hi, v)]
            samples.append(cyc)
            fh.write(json.dumps({"n": n, "t": round(time.perf_counter() - t0, 2), **row}) + "\n")
            fh.flush()
            n += 1
            print(f"{n:4}  " + "  ".join(cells), flush=True)
            if args.seconds and (time.perf_counter() - t0) >= args.seconds:
                break
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n(aborted)")
    finally:
        try:
            t.release()
        except Exception:  # noqa: BLE001
            pass
        try:
            t.close()
        except Exception:  # noqa: BLE001
            pass
        fh.close()

    # --- Correlation against RPM: the MAF must FOLLOW the rpm. This is the discriminator:
    # temp fields also have a span but do not correlate with rpm. ---
    rpm = [c.get(_RPM_KEY) for c in samples]
    rpm_vals = [x for x in rpm if x is not None]
    rpm_moved = rpm_vals and (max(rpm_vals) - min(rpm_vals) >= 100)
    if rpm_moved:
        print(f"\n=== correlation against RPM ({_RPM_KEY}) — MAF candidate on top ===")
        print(f"    (rpm moved {min(rpm_vals)}→{max(rpm_vals)} over {n} samples)")
        corrs = []
        for key in span:
            if key == _RPM_KEY:
                continue
            c = _pearson([s.get(key) for s in samples], rpm)
            if c is not None:
                corrs.append((key, c, span[key][1] - span[key][0]))
        for key, c, sp in sorted(corrs, key=lambda x: abs(x[1]), reverse=True):
            mark = "  <== follows RPM strongly" if abs(c) >= 0.9 else ("  < possible" if abs(c) >= 0.7 else "")
            print(f"  {key:8}  r={c:+.3f}  span {sp:6}{mark}")
        print("\n  MAF = highest positive r against RPM (and moves with throttle).")
    else:
        print("\n⚠ RPM did not move (engine off or no blips) — cannot correlate.")
        print("  Run again with the ENGINE RUNNING and blip the throttle to 2000–2500 rpm a few times.")

    # Span table (dynamics regardless of rpm) — kept as a reference.
    print(f"\n=== span per field ({n} reads) — most movement on top ===")
    for key, (lo, hi) in sorted(span.items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True):
        bar = "#" * min(40, (hi - lo) // 50) if hi > lo else ""
        print(f"  {key:8}  min {lo:6}  max {hi:6}  span {hi-lo:6}  {bar}")
    print(f"\nRaw data: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
