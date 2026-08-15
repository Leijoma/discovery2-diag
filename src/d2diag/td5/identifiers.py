"""Td5 ReadDataByLocalIdentifier (0x21) — kända identifiers och skalning.

Fältdefinitionerna bor numera i den deklarativa storen
:mod:`d2diag.signals` (``signals/td5.json``) — **samma fil som automap läser och
skriver**, så en bekräftad mappning hamnar direkt här utan handinklistring. Detta
modul-API (``SIGNALS``, ``BY_NAME``, ``LIDS``, ``LIMITS``, ``decode_lid`` …) är
oförändrat och härleds ur storen.

Protokollfakta (LID-nummer, offset, skalning) härledda ur referensverktyget
**Ekaitza_Itzali** (EA2EGA); ingen kod därifrån är kopierad (se
THIRD_PARTY_LICENSES.md). Offset räknas i **datafältet** (efter positiv SID 0x61
och ekad identifierare), dvs det :meth:`KWP2000.read_local_identifier` returnerar.
"""
from __future__ import annotations

from ..signals import Signal, load_signals

SIGNALS = load_signals("td5")
BY_NAME = {s.name: s for s in SIGNALS}
LIDS = sorted({s.lid for s in SIGNALS})

# Driftsintervall (min_ok, max_ok) för avvikelseflaggning — härleds ur storen.
# Signaler utan gränser flaggas inte (ext_temp = oansluten givare; maf_raw = okänd skala).
LIMITS = {s.name: s.limits for s in SIGNALS if s.limits}


def signal_status(name: str, value: "float | None") -> "str | None":
    """Returnera 'ok' / 'low' / 'high' mot driftsintervallet, eller None om
    signalen saknar intervall (flaggas ej)."""
    lim = LIMITS.get(name)
    if lim is None or value is None:
        return None
    lo, hi = lim
    if value < lo:
        return "low"
    if value > hi:
        return "high"
    return "ok"


def signals_for_lid(lid: int) -> "list[Signal]":
    return [s for s in SIGNALS if s.lid == lid]


def decode_lid(lid: int, data: bytes) -> "dict[str, float]":
    """Avkoda alla signaler i en LID ur dess datafält (hoppar över de som inte får plats)."""
    return {s.name: s.decode(data) for s in signals_for_lid(lid) if s.fits(data)}
