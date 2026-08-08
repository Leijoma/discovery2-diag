"""Frame-parsning + LID-lager för den passiva sniff-kalibreringen.

Ingesterar hex-rader (ESP32-format ``[  t] 02 21 09 2c …`` eller rå hex), spårar
aktiv modul via fast-init-signatur, och lagrar **senaste råa datafält per LID**
(ur ``61 <lid> …``-svar). Ger en snapshot till webbvyn med vår nuvarande avkodning
bredvid råbytesen.
"""
from __future__ import annotations

import re

from ..td5 import identifiers as td5id

# Fast-init-signaturer → modul (så vi vet vilken ECU LID:erna hör till).
_INIT_SIGS = {
    (0x81, 0x13, 0xF7, 0x81): "td5",
    (0x81, 0x29, 0xF7, 0x81): "slabs",
}

_HEX_AFTER_BRACKET = re.compile(r"\]\s*([0-9a-fA-F ]+)")


def parse_hex_line(line: str) -> "list[int] | None":
    """Plocka bytelistan ur en ESP32-loggrad (``[  t] hex …``) eller ren hex-rad."""
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
    """Dela bytelista i ramar via längd-prefix ``<len><payload><cs>`` (0x00 = gap)."""
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
    """Vår nuvarande avkodning av en LID (för jämförelse mot Nanacom-skärmen)."""
    out: "list[dict]" = []
    if module == "td5":
        for s in td5id.signals_for_lid(lid):
            if s.fits(data):
                out.append({
                    "name": s.name, "offset": s.offset, "kind": s.kind,
                    "value": round(s.decode(data), 3), "unit": s.unit,
                })
    elif module == "slabs" and lid == 0x54 and len(data) >= 2:
        # 21 54: höjder vänster/höger (byte0/byte1) — avkodat i SlabsDataSource.
        out.append({"name": "height_left", "offset": 0, "kind": "u8", "value": data[0], "unit": ""})
        out.append({"name": "height_right", "offset": 1, "kind": "u8", "value": data[1], "unit": ""})
    return out


class LidStore:
    """Senaste råa datafält per (modul, LID), matat ur sniffade hex-rader."""

    def __init__(self) -> None:
        self.module: "str | None" = None
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
            # ReadDataByLocalId-svar: 61 <lid> <data…>
            if len(payload) >= 2 and payload[0] == 0x61:
                lid = payload[1]
                data = bytes(payload[2:])
                mod = self.module or "?"
                slot = self._data.setdefault(mod, {}).setdefault(lid, {"count": 0})
                slot["raw"] = data
                slot["count"] = slot["count"] + 1

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
