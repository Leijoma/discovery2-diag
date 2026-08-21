#!/usr/bin/env python3
"""Analysera en rå TX/RX-logg och titta på ALL mottagen data — inte bara de fält
vi redan mappat. Varje TD5-poll ger ett helt block per LID; de bytes vi inte döpt
är precis där omappade signaler (t.ex. MAF) gömmer sig.

För varje LID visas:
  * byte-nivå: vilka byte-positioner RÖR sig (min/max/distinkta) vs konstanta
  * u16 (big-endian) på varje jämnt offset: spann + ev. korrelation mot RPM
  * vilka offset som redan är MAPPADE (ur signalstoren) vs OMAPPADE

Om RPM (21 09) rör sig rankas omappade u16-fält efter korrelation mot varvtalet —
MAF ska följa rpm. Rör sig inte rpm rankas efter spann i stället.

    PYTHONPATH=src python3 tools/raw_analyze.py                      # nyaste raw-td5-*.log
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
    """Slå ihop alla RX-bytes i loggen till EN ström (frame-parsern letar i den)."""
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
    """Plocka ut giltiga oadresserade svarsramar ``<len> 61 <lid> <payload> <cs>``.

    Validerar checksumman (summan av len+ramen & 0xFF) så vi inte fastnar på
    slumpmässiga 0x61 i eko/brus. Returnerar (lid, payload)-par i tidsordning."""
    out: "list[tuple[int, bytes]]" = []
    i, n = 0, len(stream)
    while i < n:
        fmt = stream[i]
        ln = fmt & 0x3F  # oadresserad: låga 6 bitar = längd
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
    ap.add_argument("log", nargs="?", help="rålogg (default: nyaste logs/raw-<module>-*.log)")
    ap.add_argument("--module", default="td5", help="td5 (default) eller slabs — för mappnings-facit")
    ap.add_argument("--rpm-lid", default="09", help="LID vars u16@0 är RPM (td5: 09)")
    args = ap.parse_args()

    path = args.log
    if not path:
        cands = sorted(glob.glob(f"logs/raw-{args.module}-*.log"), reverse=True)
        if not cands:
            print(f"ingen logg: logs/raw-{args.module}-*.log"); return 1
        path = cands[0]
    print(f"analyserar {path}")

    frames = _read_frames(_bytes_from_log(path))
    if not frames:
        print("inga giltiga 61-svarsramar hittades"); return 1

    # per LID: lista av payloads i tidsordning
    per: "dict[int, list[bytes]]" = {}
    for lid, payload in frames:
        per.setdefault(lid, []).append(payload)

    # mappade (lid, offset) ur signalstoren
    mapped: "set[tuple[int, int]]" = set()
    for s in load_signals(args.module):
        try:  # Signal.lid är oftast redan int; tål hex-sträng också
            lid_i = s.lid if isinstance(s.lid, int) else int(str(s.lid), 16)
            mapped.add((lid_i, int(s.offset)))
        except (ValueError, TypeError):
            pass

    rpm_lid = int(args.rpm_lid, 16)
    rpm_series = [_u16(p, 0) for p in per.get(rpm_lid, [])]
    rpm_vals = [x for x in rpm_series if x is not None]
    rpm_moved = bool(rpm_vals) and (max(rpm_vals) - min(rpm_vals) >= 100)

    print(f"ramar: {len(frames)}  ·  LID:er: {len(per)}  ·  "
          f"RPM {'rör sig '+str(min(rpm_vals))+'→'+str(max(rpm_vals)) if rpm_moved else 'STILLA (motor av?)'}")

    movers = []  # (lid, off, span, corr, mapped?)
    for lid in sorted(per):
        payloads = per[lid]
        L = max(len(p) for p in payloads)
        # byte-nivå: vilka positioner rör sig
        moving_bytes = []
        for off in range(L):
            vs = [p[off] for p in payloads if off < len(p)]
            if vs and max(vs) != min(vs):
                moving_bytes.append(off)
        tag = "".join("^" if b in moving_bytes else "." for b in range(L))
        print(f"\n21 {lid:02X}  ({len(payloads)} läsningar, {L} byte)  rörliga byte: {tag or '(inga)'}")
        # u16 på varje jämnt offset
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
                note = "  <== följer RPM (MAF-kandidat)"
            elif not ismap and not rpm_moved and span > 0:
                note = "  < rör sig"
            print(f"    @{off:<2} u16  min {min(vals):5}  max {max(vals):5}  spann {span:5}{cstr}  [{flag}]{note}")
            if not ismap and span > 0:
                movers.append((lid, off, span, corr if corr is not None else 0.0))

    print("\n=== OMAPPADE fält som rör sig — mest intressanta överst ===")
    if rpm_moved:
        movers.sort(key=lambda m: abs(m[3]), reverse=True)
        for lid, off, span, corr in movers[:12]:
            print(f"  21 {lid:02X}@{off:<2}  r(rpm)={corr:+.2f}  spann {span}")
        print("\n  MAF = högst positiv r mot RPM.")
    else:
        movers.sort(key=lambda m: m[2], reverse=True)
        for lid, off, span, _ in movers[:12]:
            print(f"  21 {lid:02X}@{off:<2}  spann {span}")
        print("\n  (RPM stilla → kan inte peka ut MAF. Fånga en logg med motorn igång.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
