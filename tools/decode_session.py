"""Decode an esp32_read log (SLABS/KWP2000) grouped per marker.

    python3 tools/decode_session.py logs/session.log

Reads `>>> marker` rows and `[  t] hex …` frames. Splits each row into frames via
the length prefix (`<len> <payload…> <cs>`, leading 0x00 = gap skipped), decodes
KWP2000 services, dedupes per marker on (SID + first params) so live-poll
repetitions collapse. Writes a compact request→response map per marker.
"""
import re
import sys

SVC = {
    0x10: "StartDiagSession", 0x14: "ClearFaults", 0x18: "ReadDTCByStatus",
    0x1A: "ReadEcuId", 0x20: "StopDiagSession", 0x21: "ReadDataLocal",
    0x23: "ReadMemByAddr", 0x27: "SecurityAccess", 0x2E: "WriteDataCommon",
    0x2F: "IOControl", 0x31: "StartRoutine", 0x32: "StopRoutine",
    0x33: "RoutineResults", 0x3B: "WriteDataLocal", 0x3E: "TesterPresent",
}


def frames(b):
    """Split a byte list into frames via the length prefix. Skip leading 0x00 (gap)."""
    out, i, n = [], 0, len(b)
    while i < n:
        if b[i] == 0x00:
            i += 1; continue
        ln = b[i]
        if ln == 0 or i + 1 + ln + 1 > n:
            break
        out.append(b[i:i + 1 + ln + 1])
        i += 1 + ln + 1
    return out


def decode(fr):
    """→ (sig, text). sig = dedup key."""
    if len(fr) < 3:
        return None, None
    pl = fr[1:1 + fr[0]]
    if not pl:
        return None, None
    sid = pl[0]
    hx = " ".join(f"{v:02x}" for v in pl)
    if sid == 0x7F:
        svc = SVC.get(pl[1], hex(pl[1])) if len(pl) > 1 else "?"
        return (0x7F, pl[1] if len(pl) > 1 else 0), f"NEG {svc} NRC={pl[2]:#04x}" if len(pl) > 2 else "NEG"
    base = sid & ~0x40
    resp = bool(sid & 0x40) and base in SVC
    name = SVC.get(base if resp else sid)
    if name is None:
        return (sid, tuple(pl[1:3])), f"? {hx}"
    kind = "RESP" if resp else "REQ "
    sub = " ".join(f"{v:02x}" for v in pl[1:4])
    data = " ".join(f"{v:02x}" for v in pl[1:])
    sig = (sid, tuple(pl[1:3]))
    return sig, f"{kind} {name:15s} {data}"


def main():
    path = sys.argv[1]
    marker = "(start)"
    order, groups = [marker], {marker: ([], set())}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip()
        if ">>>" in line:
            marker = line.split(">>>", 1)[1].strip()
            if marker not in groups:
                groups[marker] = ([], set()); order.append(marker)
            continue
        m = re.search(r"\]\s*([0-9a-fA-F ]+)", line)
        if not m:
            continue
        b = [int(t, 16) for t in m.group(1).split() if len(t) == 2]
        seen_list, seen_set = groups[marker]
        for fr in frames(b):
            sig, text = decode(fr)
            if text is None or sig is None:
                continue
            # skip keepalive (TesterPresent) + pure memory polls in the summary
            if sig[0] in (0x3E, 0x7E):
                continue
            if sig not in seen_set:
                seen_set.add(sig); seen_list.append(text)
    for mk in order:
        rows, _ = groups[mk]
        if not rows:
            continue
        print(f"\n=== {mk} ===")
        for r in rows:
            print("  " + r)


if __name__ == "__main__":
    raise SystemExit(main())
