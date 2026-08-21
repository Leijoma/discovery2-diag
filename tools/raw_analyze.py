#!/usr/bin/env python3
"""Analyze a raw TX/RX log and look at ALL received data — not just the fields
we've already mapped. Every TD5 poll returns a whole block per LID; the bytes we
haven't named are exactly where unmapped signals (e.g. MAF) hide.

For each LID it shows:
  * byte level: which byte positions MOVE (min/max/distinct) vs constant
  * u16 (big-endian) at each even offset: range + optional correlation against RPM
  * which offsets are already MAPPED (from the signal store) vs UNMAPPED

If RPM (21 09) moves, unmapped u16 fields are ranked by correlation against engine
speed — MAF should track rpm. If rpm doesn't move, they're ranked by range instead.

    PYTHONPATH=src python3 tools/raw_analyze.py                      # newest raw-td5-*.log
    PYTHONPATH=src python3 tools/raw_analyze.py logs/raw-td5-XXduration.log
    PYTHONPATH=src python3 tools/raw_analyze.py --module slabs
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from d2diag.signals import load_signals  # noqa: E402

_RX = re.compile(r"\bRX\b\s+([0-9A-Fa-f ]+)")


def _bytes_from_log(path: str) -> bytes:
    """Merge all RX bytes in the log into ONE stream (the frame parser searches it)."""
    buf = bytearray()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _RX.search(line)
            if m:
                for tok in m.group(1).split():
                    try:
                        buf.append(int(tok, 16))
                    except ValueError:
                        pass
    return bytes(buf)


def _read_frames(stream: bytes) -> "list[tuple[int, bytes]]":
    """Extract valid unaddressed response frames ``<len> 61 <lid> <payload> <cs>``.

    Validates the checksum (sum of len+frame & 0xFF) so we don't trip on random
    0x61 in echo/noise. Returns (lid, payload) pairs in time order."""
    out: "list[tuple[int, bytes]]" = []
    i, n = 0, len(stream)
    while i < n:
        fmt = stream[i]
        ln = fmt & 0x3F  # unaddressed: low 6 bits = length
        if 2 <= ln <= 63 and i + 1 + ln < n:
            frame = stream[i + 1:i + 1 + ln]
            cs = stream[i + 1 + ln]
            if (fmt + sum(frame)) & 0xFF == cs and frame[0] == 0x61:
                out.append((frame[1], bytes(frame[2:])))
                i += 2 + ln
                continue
        i += 1
    return out


def _u16(b: bytes, off: int) -> "int | None":
    return int.from_bytes(b[off:off + 2], "big") if off + 2 <= len(b) else None


def _pearson(xs, ys) -> "float | None":
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    if sxx == 0 or syy == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / (sxx * syy) ** 0.5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", nargs="?", help="raw log (default: newest logs/raw-<module>-*.log)")
    ap.add_argument("--module", default="td5", help="td5 (default) or slabs — for the mapping reference")
    ap.add_argument("--rpm-lid", default="09", help="LID whose u16@0 is RPM (td5: 09)")
    args = ap.parse_args()

    path = args.log
    if not path:
        cands = sorted(glob.glob(f"logs/raw-{args.module}-*.log"), reverse=True)
        if not cands:
            print(f"no log: logs/raw-{args.module}-*.log"); return 1
        path = cands[0]
    print(f"analyzing {path}")

    frames = _read_frames(_bytes_from_log(path))
    if not frames:
        print("no valid 61 response frames found"); return 1

    # per LID: list of payloads in time order
    per: "dict[int, list[bytes]]" = {}
    for lid, payload in frames:
        per.setdefault(lid, []).append(payload)

    # mapped (lid, offset) from the signal store
    mapped: "set[tuple[int, int]]" = set()
    for s in load_signals(args.module):
        try:  # Signal.lid is usually already an int; also tolerates a hex string
            lid_i = s.lid if isinstance(s.lid, int) else int(str(s.lid), 16)
            mapped.add((lid_i, int(s.offset)))
        except (ValueError, TypeError):
            pass

    rpm_lid = int(args.rpm_lid, 16)
    rpm_series = [_u16(p, 0) for p in per.get(rpm_lid, [])]
    rpm_vals = [x for x in rpm_series if x is not None]
    rpm_moved = bool(rpm_vals) and (max(rpm_vals) - min(rpm_vals) >= 100)

    print(f"frames: {len(frames)}  ·  LIDs: {len(per)}  ·  "
          f"RPM {'moves '+str(min(rpm_vals))+'→'+str(max(rpm_vals)) if rpm_moved else 'STILL (engine off?)'}")

    movers = []  # (lid, off, span, corr, mapped?)
    for lid in sorted(per):
        payloads = per[lid]
        L = max(len(p) for p in payloads)
        # byte level: which positions move
        moving_bytes = []
        for off in range(L):
            vs = [p[off] for p in payloads if off < len(p)]
            if vs and max(vs) != min(vs):
                moving_bytes.append(off)
        tag = "".join("^" if b in moving_bytes else "." for b in range(L))
        print(f"\n21 {lid:02X}  ({len(payloads)} reads, {L} bytes)  moving bytes: {tag or '(none)'}")
        # u16 at each even offset
        for off in range(0, L - 1, 2):
            series = [_u16(p, off) for p in per[lid]]
            vals = [x for x in series if x is not None]
            if not vals:
                continue
            span = max(vals) - min(vals)
            ismap = (lid, off) in mapped
            corr = _pearson(series, rpm_series) if (rpm_moved and lid != rpm_lid) else None
            cstr = f" r(rpm)={corr:+.2f}" if corr is not None else ""
            flag = "MAP " if ismap else "  · "
            note = ""
            if not ismap and rpm_moved and corr is not None and abs(corr) >= 0.8:
                note = "  <== tracks RPM (MAF candidate)"
            elif not ismap and not rpm_moved and span > 0:
                note = "  < moves"
            print(f"    @{off:<2} u16  min {min(vals):5}  max {max(vals):5}  range {span:5}{cstr}  [{flag}]{note}")
            if not ismap and span > 0:
                movers.append((lid, off, span, corr if corr is not None else 0.0))

    print("\n=== UNMAPPED fields that move — most interesting first ===")
    if rpm_moved:
        movers.sort(key=lambda m: abs(m[3]), reverse=True)
        for lid, off, span, corr in movers[:12]:
            print(f"  21 {lid:02X}@{off:<2}  r(rpm)={corr:+.2f}  range {span}")
        print("\n  MAF = highest positive r against RPM.")
    else:
        movers.sort(key=lambda m: m[2], reverse=True)
        for lid, off, span, _ in movers[:12]:
            print(f"  21 {lid:02X}@{off:<2}  range {span}")
        print("\n  (RPM still → can't pinpoint MAF. Capture a log with the engine running.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
