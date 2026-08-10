"""Analysera en esp32_read-logg → request/response/annotation/candidate.

Vänder ChatGPT-analysens metod till kod:
- **Ram + checksum:** längd-prefixade KWP-ramar `<len><payload><cs>` (cs = summa av
  alla föregående byte mod 256) valideras. Rena ramar (TD5/SLABS) klassas per tjänst.
- **Andra protokoll** (Autobox `72…`, ACE `67…/04 04 00`, Airbag `…90 04…`, BCU) visas
  som råramar med igenkänd funktions-signatur.
- **Annotering mitt i flödet:** varje `>>> markör` ankras RETROAKTIVT — vi visar
  distinkta ramar i ett fönster runt markören och kollapsar keepalive/upprepningar,
  så en kommentar mitt i en ström ändå knyts till rätt trafikregim.
- **Skärm-fingerprint:** vilka `21 xx`-identifierare som pollas repeterat.

    python3 tools/analyze_capture.py logs/faultread-20260809.log
    python3 tools/analyze_capture.py logs/session.log --window 6
"""
from __future__ import annotations

import argparse
import re
import sys

SERVICES = {
    0x10: "StartDiagSession", 0x14: "ClearFaults", 0x18: "ReadDTC",
    0x1A: "ReadEcuId", 0x20: "StopDiagSession", 0x21: "ReadLocalId",
    0x27: "SecurityAccess", 0x2E: "WriteDataCommon", 0x2F: "IOControl2F",
    0x30: "IOControl", 0x31: "StartRoutine", 0x33: "RoutineResults",
    0x3B: "WriteLocalId", 0x3E: "TesterPresent",
}
_LINE = re.compile(r"\[\s*(\d+)\s*\]\s*([0-9a-fA-F ]+)")


def parse(path: str):
    """→ lista av (ms, kind, payload). kind = 'data' (bytes) | 'mark' (text)."""
    events = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip()
        if ">>>" in line:
            events.append((_last_ms(events), "mark", line.split(">>>", 1)[1].strip()))
            continue
        m = _LINE.search(line)
        if not m:
            continue
        ms = int(m.group(1))
        b = [int(t, 16) for t in m.group(2).split() if len(t) == 2]
        if b:
            events.append((ms, "data", b))
    return events


def _last_ms(events):
    for ms, kind, _ in reversed(events):
        if kind == "data":
            return ms
    return 0


def split_frames(b):
    """Dela en bytelista i längd-prefixade ramar. → (frames, consumed).

    En ram = [len, payload…, cs] med giltig additiv checksum. Stannar vid första
    byte som inte inleder en giltig ram (0x00-gap hoppas)."""
    out, i, n = [], 0, len(b)
    while i < n:
        if b[i] == 0x00:
            i += 1
            continue
        ln = b[i]
        if ln == 0 or i + 1 + ln + 1 > n:
            break
        frame = b[i : i + 1 + ln + 1]
        if (sum(frame[:-1]) & 0xFF) != frame[-1]:
            break
        out.append(frame)
        i += 1 + ln + 1
    return out, i


def classify(frame):
    """→ kort textbeskrivning av en giltig KWP-ram."""
    payload = frame[1:-1]
    if not payload:
        return "(tom)"
    sid = payload[0]
    hx = " ".join(f"{v:02x}" for v in payload)
    base = sid & ~0x40
    if sid & 0x40 and base in SERVICES:
        return f"RESP {SERVICES[base]:14s} {hx}"
    name = SERVICES.get(sid, f"?{sid:02x}")
    return f"REQ  {name:14s} {hx}"


def frame_sig(b):
    return tuple(b)


def raw_hint(b):
    """Igenkänning för icke-KWP-ramar (Autobox/ACE/Airbag/BCU)."""
    if len(b) >= 3 and b[0] == 0x72:
        return "AUTOBOX-cmd"
    if b[:2] == [0x04, 0x04] or b[:2] == [0x07, 0x07] or b[:2] == [0x67, 0x67]:
        return "ACE"
    if 0x90 in b and (0x61 in b or 0x21 in b):
        return "AIRBAG-record?"
    if 0xCC in b and (0x21 in b or 0x3B in b):
        return "BCU-EKA?"
    return ""


def analyze(path: str, window_s: float = 6.0):
    events = parse(path)
    win = int(window_s * 1000)
    # Markörer med index
    marks = [(i, ms, txt) for i, (ms, k, txt) in enumerate(events) if k == "mark"]
    print(f"### {path}  ({sum(1 for _,k,_ in events if k=='data')} datarader, {len(marks)} markörer)\n")

    # Skärm-fingerprint: vilka 21 xx pollas mest?
    lids = {}
    for ms, k, p in events:
        if k != "data":
            continue
        frames, _ = split_frames(p)
        for f in frames:
            pl = f[1:-1]
            if pl and pl[0] == 0x21 and len(pl) >= 2:
                lids[pl[1]] = lids.get(pl[1], 0) + 1
    if lids:
        top = sorted(lids.items(), key=lambda x: -x[1])[:12]
        print("Mest pollade 21-identifierare (skärm-fingerprint):")
        print("  " + ", ".join(f"21 {l:02x}(×{c})" for l, c in top) + "\n")

    # Per markör: distinkta ramar i [markör−window, markör+2s], keepalive kollapsad
    for i, ms, txt in marks:
        lo, hi = ms - win, ms + 2000
        seen, rows = set(), []
        for ems, k, p in events:
            if k != "data" or not (lo <= ems <= hi):
                continue
            frames, consumed = split_frames(p)
            for f in frames:
                sig = frame_sig(f)
                pl = f[1:-1]
                if pl and pl[0] in (0x3E, 0x7E):  # keepalive
                    continue
                if sig in seen:
                    continue
                seen.add(sig)
                rows.append("  " + classify(f))
            rest = p[consumed:]
            if rest:  # icke-KWP-ram (annat protokoll)
                sig = ("raw",) + tuple(rest)
                if sig in seen or set(rest) <= {0x00}:
                    continue
                seen.add(sig)
                hint = raw_hint(rest)
                rows.append("  RAW  " + " ".join(f"{v:02x}" for v in rest) + (f"   [{hint}]" if hint else ""))
        if rows:
            print(f">>> {txt}   @{ms}ms")
            for r in rows[:12]:
                print(r)
            if len(rows) > 12:
                print(f"  … (+{len(rows)-12} till)")
            print()


def variance(path: str):
    """Vilka byte-offset VARIERAR per LID? = differential-kandidater ur befintlig data.

    Konstant offset = statiskt fält; varierande = det som rörde sig under captet
    (kandidat att korrelera mot Nanacom-värde/fysisk ändring)."""
    from collections import defaultdict
    resp = defaultdict(list)
    for ms, k, p in parse(path):
        if k != "data":
            continue
        for f, _ in [(f, 0) for f in split_frames(p)[0]]:
            pl = f[1:-1]
            if pl and pl[0] == 0x61 and len(pl) >= 2:
                resp[pl[1]].append(tuple(pl[2:]))
    print(f"### Byte-varians per 21-LID — {path}\n")
    for lid in sorted(resp):
        vals = resp[lid]
        uniq = list(dict.fromkeys(vals))
        if not uniq:
            continue
        n = min(len(v) for v in uniq)
        varying = [i for i in range(n) if len({v[i] for v in uniq}) > 1]
        tag = "VARIERAR " + str(varying) if varying else "konstant"
        print(f"21 {lid:02x}: {len(vals):>4} svar, {len(uniq):>3} distinkta, {n} byte — {tag}")
        if varying:
            for v in uniq[:3]:
                print("        " + " ".join(f"{x:02x}" for x in v))


def main():
    ap = argparse.ArgumentParser(description="Analysera esp32_read-capture")
    ap.add_argument("log")
    ap.add_argument("--window", type=float, default=6.0, help="retroaktivt fönster (s) före markör")
    ap.add_argument("--variance", action="store_true", help="byte-varians per LID (differential-kandidater)")
    args = ap.parse_args()
    if args.variance:
        variance(args.log)
    else:
        analyze(args.log, args.window)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
