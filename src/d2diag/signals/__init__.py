"""Deklarativ signalstore — enda sanningskällan för LID-fältmappningar.

En ``<modul>.json`` per ECU beskriver varje fält (offset, typ, skala, bias, enhet,
konfidens, gränser, ev. bit/tillstånd). Både **avkodarna** (Td5/Slabs/UI) och
**automap** läser samma fil, och en bekräftad mappning skrivs tillbaka med
:func:`upsert_field` — så hand-inklistrandet av ``Signal(...)``-rader försvinner.

Konfidens: ``belagt`` (verifierat mot bilen) vs ``kandidat`` (härlett/overifierat).
Håll isär det (jfr projektkonventionen "skilj på belagt och slutsatsdraget").
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DIR = Path(__file__).resolve().parent


# ---- byte-läsare -------------------------------------------------------- #
def _u8(d: bytes, o: int) -> int:
    return d[o]


def _u16(d: bytes, o: int) -> int:
    return (d[o] << 8) | d[o + 1]


def _u16le(d: bytes, o: int) -> int:
    return (d[o + 1] << 8) | d[o]


def _s16(d: bytes, o: int) -> int:
    v = _u16(d, o)
    return v - 0x10000 if v >= 0x8000 else v


def _s16le(d: bytes, o: int) -> int:
    v = _u16le(d, o)
    return v - 0x10000 if v >= 0x8000 else v


_READERS = {"u8": _u8, "u16": _u16, "u16le": _u16le, "s16": _s16, "s16le": _s16le}
_WIDTH = {"u8": 1, "u16": 2, "u16le": 2, "s16": 2, "s16le": 2, "bit": 1}


@dataclass(frozen=True)
class Signal:
    """Ett avkodbart fält i en LID. Fältordningen är bakåtkompatibel med den gamla
    ``td5.identifiers.Signal`` (namn, lid, offset, kind, scale, bias, unit) — nya
    fält har defaultvärden och bryter inte positionell konstruktion."""

    name: str
    lid: int
    offset: int
    kind: str = "u16"
    scale: float = 1.0
    bias: float = 0.0
    unit: str = ""
    confidence: str = "belagt"
    limits: "tuple[float, float] | None" = None
    bit: "int | None" = None                       # för kind="bit"
    states: "dict[int, str] | None" = None          # rå värde → etikett (bit/state)
    source: str = ""

    def decode(self, data: bytes) -> float:
        """Numeriskt värde (bit → 0.0/1.0) så ``dict[str, float]``-kontraktet håller."""
        if self.kind == "bit":
            raw = (data[self.offset] >> (self.bit or 0)) & 1
        else:
            raw = _READERS[self.kind](data, self.offset)
        return raw * self.scale + self.bias

    def decode_named(self, data: bytes) -> "str | None":
        """Tillståndsetikett ur ``states`` (för UI), annars ``None``."""
        if not self.states:
            return None
        if self.kind == "bit":
            raw = (data[self.offset] >> (self.bit or 0)) & 1
        else:
            raw = int(_READERS.get(self.kind, _u8)(data, self.offset))
        return self.states.get(raw)

    def fits(self, data: bytes) -> bool:
        return len(data) >= self.offset + _WIDTH.get(self.kind, 2)


# ---- ladda / spara ------------------------------------------------------ #
def _record_to_signal(r: dict) -> Signal:
    states = r.get("states")
    if states:
        states = {int(k): v for k, v in states.items()}
    limits = r.get("limits")
    return Signal(
        name=r["name"],
        lid=int(r["lid"], 16) if isinstance(r["lid"], str) else int(r["lid"]),
        offset=int(r["offset"]),
        kind=r.get("kind", "u16"),
        scale=float(r.get("scale", 1.0)),
        bias=float(r.get("bias", 0.0)),
        unit=r.get("unit", ""),
        confidence=r.get("confidence", "kandidat"),
        limits=tuple(limits) if limits else None,
        bit=r.get("bit"),
        states=states or None,
        source=r.get("source", ""),
    )


def _path(module: str) -> Path:
    return _DIR / f"{module}.json"


def load_records(module: str) -> "list[dict]":
    """Rå JSON-poster för en modul (tom lista om filen saknas)."""
    p = _path(module)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


_CACHE: "dict[str, list[Signal]]" = {}


def load_signals(module: str) -> "list[Signal]":
    """Ladda en moduls signaler som :class:`Signal`-objekt (cachas per modul;
    cachen rensas av :func:`upsert_field`). Live-avkodare kan alltså anropa detta
    ofta utan att läsa filen varje gång."""
    if module not in _CACHE:
        _CACHE[module] = [_record_to_signal(r) for r in load_records(module)]
    return _CACHE[module]


def upsert_field(module: str, record: dict) -> None:
    """Skriv en bekräftad/kandidat-mappning till storen (write-back).

    Ersätter en befintlig post med samma ``(lid, offset, name)``, annars append.
    Default ``confidence="kandidat"``. Atomär omskrivning (temp + rename) så filen
    aldrig blir halvskriven."""
    def _norm_lid(v) -> str:
        return f"{(int(v, 16) if isinstance(v, str) else int(v)):02X}"

    rec = dict(record)
    rec.setdefault("confidence", "kandidat")
    rec["lid"] = _norm_lid(rec["lid"])
    key = (rec["lid"], int(rec["offset"]), rec["name"])
    rows = load_records(module)
    for i, r in enumerate(rows):
        if (_norm_lid(r["lid"]), int(r["offset"]), r["name"]) == key:
            rows[i] = rec
            break
    else:
        rows.append(rec)
    p = _path(module)
    fd, tmp = tempfile.mkstemp(dir=str(_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)
        _CACHE.pop(module, None)  # invalidera så nästa load ser den nya posten
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
