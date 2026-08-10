"""Delad capture-parsning — grund för analys-verktyg och protokollbibliotek.

Läser esp32_read-loggar, delar i längd-prefixade KWP-ramar med checksum-validering,
klassar tjänster och parar request→response. Håller reda på aktiv modul via
fast-init-signatur. Icke-KWP-protokoll (Autobox `72…`, BCU EKA `CC`) känns igen
separat i :mod:`d2diag.sniff.library`.
"""
from __future__ import annotations

import re

SERVICES = {
    0x10: "StartDiagSession", 0x14: "ClearFaults", 0x18: "ReadDTC",
    0x1A: "ReadEcuId", 0x20: "StopDiagSession", 0x21: "ReadLocalId",
    0x27: "SecurityAccess", 0x2E: "WriteDataCommon", 0x2F: "IOControl2F",
    0x30: "IOControl", 0x31: "StartRoutine", 0x33: "RoutineResults",
    0x3B: "WriteLocalId", 0x3E: "TesterPresent",
}
_LINE = re.compile(r"\[\s*(\d+)\s*\]\s*([0-9a-fA-F ]+)")
_INIT = {
    (0x81, 0x13, 0xF7, 0x81): "td5",
    (0x81, 0x29, 0xF7, 0x81): "slabs",
}


def parse_log(path: str) -> "list[tuple]":
    """→ [(ms, kind, payload)]. kind = 'data' (list[int]) | 'mark' (str)."""
    events: "list[tuple]" = []
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


def _last_ms(events) -> int:
    for ms, kind, _ in reversed(events):
        if kind == "data":
            return ms
    return 0


def split_frames(b: "list[int]") -> "tuple[list, int]":
    """Dela bytelista i giltiga längd-prefixade ramar. → (frames, consumed_index)."""
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


def _contains(seq, sub) -> bool:
    n = len(sub)
    return any(tuple(seq[i : i + n]) == sub for i in range(len(seq) - n + 1))


def classify_frame(frame: "list[int]") -> "dict":
    """→ {dir, sid, service, lid, payload(hex), cs_ok} för en KWP-ram."""
    payload = frame[1:-1]
    sid = payload[0] if payload else 0
    if sid == 0x7F:  # negativt svar: 7F <service> <NRC>
        return {"dir": "neg", "sid": 0x7F,
                "service": f"NegResp({SERVICES.get(payload[1], hex(payload[1])) if len(payload) >= 2 else '?'})",
                "lid": None, "payload": " ".join(f"{v:02x}" for v in payload),
                "cs_ok": (sum(frame[:-1]) & 0xFF) == frame[-1]}
    base = sid & ~0x40
    is_resp = bool(sid & 0x40) and base in SERVICES
    return {
        "dir": "resp" if is_resp else "req",
        "sid": sid,
        "service": SERVICES.get(base if is_resp else sid),
        "lid": payload[1] if len(payload) >= 2 else None,
        "payload": " ".join(f"{v:02x}" for v in payload),
        "cs_ok": (sum(frame[:-1]) & 0xFF) == frame[-1],
    }


def frames_with_context(events) -> "list[dict]":
    """Alla giltiga KWP-ramar i ordning, taggade med modul + senaste annotering.

    Returnerar även resten (icke-KWP-bytes) per rad som ``raw``-poster."""
    out: "list[dict]" = []
    module, mark = None, None
    for ms, kind, p in events:
        if kind == "mark":
            mark = p
            continue
        for sig, name in _INIT.items():
            if _contains(p, sig):
                module = name
        frames, consumed = split_frames(p)
        for f in frames:
            out.append({"ms": ms, "module": module, "annotation": mark, "kwp": classify_frame(f)})
        rest = p[consumed:]
        if rest and set(rest) - {0x00}:
            out.append({"ms": ms, "module": module, "annotation": mark,
                        "raw": " ".join(f"{v:02x}" for v in rest)})
    return out


def kwp_transactions(events) -> "list[dict]":
    """Para request→response bland KWP-ramarna (hoppar TesterPresent)."""
    fr = [e for e in frames_with_context(events) if "kwp" in e]
    txs: "list[dict]" = []
    for i, e in enumerate(fr):
        c = e["kwp"]
        if c["dir"] != "req" or c["sid"] == 0x3E:
            continue
        want = c["sid"] | 0x40
        resp = None
        for j in range(i + 1, min(i + 6, len(fr))):
            cj = fr[j]["kwp"]
            if cj["sid"] == want and (c["lid"] is None or cj["lid"] == c["lid"]):
                resp = cj
                break
        txs.append({
            "module": e["module"], "ms": e["ms"], "annotation": e["annotation"],
            "req": c["payload"], "service": c["service"], "lid": c["lid"],
            "resp": resp["payload"] if resp else None,
            "cs_ok": c["cs_ok"] and (resp["cs_ok"] if resp else True),
        })
    return txs
