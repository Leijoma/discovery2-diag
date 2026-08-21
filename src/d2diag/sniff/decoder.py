"""Frame parsing + LID layer for the passive sniff calibration.

Ingests hex lines (ESP32 format ``[  t] 02 21 09 2c …`` or raw hex), tracks the
active module via the fast-init signature, and stores the **latest raw data field per LID**
(from ``61 <lid> …`` responses). Provides a snapshot to the web view with our current
decoding next to the raw bytes.
"""
from __future__ import annotations

import re

from ..signals import load_signals

# Fast-init signatures → module (so we know which ECU the LIDs belong to).
_INIT_SIGS = {
    (0x81, 0x13, 0xF7, 0x81): "td5",
    (0x81, 0x29, 0xF7, 0x81): "slabs",
}

_HEX_AFTER_BRACKET = re.compile(r"\]\s*([0-9a-fA-F ]+)")


def parse_hex_line(line: str) -> "list[int] | None":
    """Pick the byte list out of an ESP32 log line (``[  t] hex …``) or a plain hex line."""
    if ">>>" in line or "===" in line:
        return None
    m = _HEX_AFTER_BRACKET.search(line)
    body = m.group(1) if m else line
    out = [int(t, 16) for t in body.split() if len(t) == 2 and _is_hex(t)]
    return out or None


def _is_hex(t: str) -> bool:
    try:
        int(t, 16)
        return True
    except ValueError:
        return False


def _frames(b: "list[int]") -> "list[list[int]]":
    """Split a byte list into frames via length prefix ``<len><payload><cs>`` (0x00 = gap)."""
    out, i, n = [], 0, len(b)
    while i < n:
        if b[i] == 0x00:
            i += 1
            continue
        ln = b[i]
        if ln == 0 or i + 1 + ln + 1 > n:
            break
        out.append(b[i : i + 1 + ln + 1])
        i += 1 + ln + 1
    return out


def _contains(seq: "list[int]", sub: "tuple[int, ...]") -> bool:
    n = len(sub)
    return any(tuple(seq[i : i + n]) == sub for i in range(len(seq) - n + 1))


def decode_known(module: str, lid: int, data: bytes) -> "list[dict]":
    """Our current decoding of a LID (for comparison against the reference tool screen).

    Module-generic: reads the field definitions from the declarative store
    (:mod:`d2diag.signals`). A field with ``states`` (e.g. any_door) gives its
    state label as ``value``; the rest give their numeric value."""
    out: "list[dict]" = []
    for s in load_signals(module):
        if s.lid != lid or not s.fits(data):
            continue
        named = s.decode_named(data)
        if named is not None:
            kind = f"bit{s.bit}" if s.kind == "bit" else s.kind
            out.append({"name": s.name, "offset": s.offset, "kind": kind,
                        "value": named, "unit": s.unit})
        else:
            out.append({"name": s.name, "offset": s.offset, "kind": s.kind,
                        "value": round(s.decode(data), 3), "unit": s.unit})
    return out


class LidStore:
    """Latest raw data field per (module, LID), fed from sniffed hex lines."""

    def __init__(self) -> None:
        self.module: "str | None" = None
        self.frames = 0  # total number of decoded response frames (for freshness measurement)
        self._data: "dict[str, dict[int, dict]]" = {}

    def ingest_line(self, line: str) -> None:
        b = parse_hex_line(line)
        if b:
            self.ingest_bytes(b)

    def ingest_bytes(self, b: "list[int]") -> None:
        for sig, name in _INIT_SIGS.items():
            if _contains(b, sig):
                self.module = name
        for fr in _frames(b):
            payload = fr[1 : 1 + fr[0]]
            # ReadDataByLocalId response: 61 <lid> <data…>
            if len(payload) >= 2 and payload[0] == 0x61:
                lid = payload[1]
                data = bytes(payload[2:])
                mod = self.module or "?"
                slot = self._data.setdefault(mod, {}).setdefault(lid, {"count": 0})
                slot["raw"] = data
                slot["count"] = slot["count"] + 1
                self.frames += 1

    def snapshot(self, module: "str | None" = None) -> "dict":
        mod = module or self.module
        md = self._data.get(mod or "", {})
        lids = []
        for lid in sorted(md):
            raw = md[lid].get("raw", b"")
            lids.append({
                "lid": f"{lid:02x}",
                "raw": raw.hex(" "),
                "count": md[lid]["count"],
                "decode": decode_known(mod or "", lid, raw),
            })
        return {"module": mod, "modules": sorted(self._data), "lids": lids}
