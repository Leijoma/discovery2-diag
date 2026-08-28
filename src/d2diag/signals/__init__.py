"""Declarative signal store — the single source of truth for LID field mappings.

One ``<module>.json`` per ECU describes each field (offset, type, scale, bias, unit,
confidence, limits, optional bit/state). Both the **decoders** (Td5/Slabs/UI) and
**automap** read the same file, and a confirmed mapping is written back with
:func:`upsert_field` — so the hand-pasting of ``Signal(...)`` rows goes away.

Confidence: ``belagt`` (verified against the car) vs ``kandidat`` (derived/unverified).
Keep them apart (cf. the project convention "distinguish proven from inferred").
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DIR = Path(__file__).resolve().parent


# ---- byte readers ------------------------------------------------------- #
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
    """A decodable field in a LID. The field order is backward-compatible with the old
    ``td5.identifiers.Signal`` (name, lid, offset, kind, scale, bias, unit) — new
    fields have default values and don't break positional construction."""

    name: str
    lid: int
    offset: int
    kind: str = "u16"
    scale: float = 1.0
    bias: float = 0.0
    unit: str = ""
    confidence: str = "belagt"
    limits: "tuple[float, float] | None" = None
    bit: "int | None" = None                       # for kind="bit"
    states: "dict[int, str] | None" = None          # raw value → label (bit/state)
    source: str = ""

    def decode(self, data: bytes) -> float:
        """Numeric value (bit → 0.0/1.0) so the ``dict[str, float]`` contract holds."""
        if self.kind == "bit":
            raw = (data[self.offset] >> (self.bit or 0)) & 1
        else:
            raw = _READERS[self.kind](data, self.offset)
        return raw * self.scale + self.bias

    def decode_named(self, data: bytes) -> "str | None":
        """State label from ``states`` (for the UI), otherwise ``None``."""
        if not self.states:
            return None
        if self.kind == "bit":
            raw = (data[self.offset] >> (self.bit or 0)) & 1
        else:
            raw = int(_READERS.get(self.kind, _u8)(data, self.offset))
        return self.states.get(raw)

    def fits(self, data: bytes) -> bool:
        return len(data) >= self.offset + _WIDTH.get(self.kind, 2)


# ---- load / save -------------------------------------------------------- #
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
    """Raw JSON records for a module (empty list if the file is missing)."""
    p = _path(module)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


_CACHE: "dict[str, list[Signal]]" = {}


def load_signals(module: str) -> "list[Signal]":
    """Load a module's signals as :class:`Signal` objects (cached per module;
    the cache is cleared by :func:`upsert_field`). Live decoders can therefore call this
    often without reading the file every time."""
    if module not in _CACHE:
        _CACHE[module] = [_record_to_signal(r) for r in load_records(module)]
    return _CACHE[module]


def upsert_field(module: str, record: dict) -> None:
    """Write a confirmed/candidate mapping to the store (write-back).

    Replaces an existing record with the same ``(lid, offset, name)``, otherwise appends.
    Default ``confidence="kandidat"``. Atomic rewrite (temp + rename) so the file
    never ends up half-written."""
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
        _CACHE.pop(module, None)  # invalidate so the next load sees the new record
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def remove_field(module: str, lid, offset: int, bit: "int | None" = None) -> int:
    """Remove stored field(s) at ``(lid, offset)`` — and, when ``bit`` is given, only the bit
    field with that bit index. Returns how many records were removed. Atomic rewrite. Used to
    reassign/clear a bit in the mapper (upsert keys on name, so a rename would otherwise orphan
    the old record)."""
    def _norm_lid(v) -> str:
        return f"{(int(v, 16) if isinstance(v, str) else int(v)):02X}"

    key_lid, off = _norm_lid(lid), int(offset)

    def _match(r: dict) -> bool:
        if _norm_lid(r["lid"]) != key_lid or int(r["offset"]) != off:
            return False
        return bit is None or (r.get("kind") == "bit" and int(r.get("bit", -1)) == int(bit))

    rows = load_records(module)
    kept = [r for r in rows if not _match(r)]
    removed = len(rows) - len(kept)
    if removed:
        p = _path(module)
        fd, tmp = tempfile.mkstemp(dir=str(_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(kept, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, p)
            _CACHE.pop(module, None)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return removed
