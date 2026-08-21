"""Td5 ReadDataByLocalIdentifier (0x21) — known identifiers and scaling.

The field definitions now live in the declarative store
:mod:`d2diag.signals` (``signals/td5.json``) — **the same file automap reads and
writes**, so a confirmed mapping ends up here directly without hand-pasting. This
module API (``SIGNALS``, ``BY_NAME``, ``LIDS``, ``LIMITS``, ``decode_lid`` …) is
unchanged and is derived from the store.

Protocol facts (LID numbers, offset, scaling) derived from the reference tool
**Ekaitza_Itzali** (EA2EGA); no code from it is copied (see
THIRD_PARTY_LICENSES.md). Offset is counted in the **data field** (after positive SID 0x61
and the echoed identifier), i.e. what :meth:`KWP2000.read_local_identifier` returns.
"""
from __future__ import annotations

from ..signals import Signal, load_signals

SIGNALS = load_signals("td5")
BY_NAME = {s.name: s for s in SIGNALS}
LIDS = sorted({s.lid for s in SIGNALS})

# Operating range (min_ok, max_ok) for deviation flagging — derived from the store.
# Signals without limits are not flagged (ext_temp = unconnected sensor; maf_raw = unknown scale).
LIMITS = {s.name: s.limits for s in SIGNALS if s.limits}


def signal_status(name: str, value: "float | None") -> "str | None":
    """Return 'ok' / 'low' / 'high' / 'suspect' against the operating range, or
    None if the signal has no range (not flagged).

    ``suspect`` = physically implausible value (outside the range by more than its
    ENTIRE span) → almost certainly a noisy misread, not real data. Proven on the
    motorway 2026-08-21: the KKL cable throws occasional spikes (MAP 4.5 bar, coolant
    429°, throttle 41 V) that pass framing but are garbage. Flagged — NOT hidden, since
    a genuine sensor dropout (IAT dropping out) is also "suspect" and IS the signal.
    """
    lim = LIMITS.get(name)
    if lim is None or value is None:
        return None
    lo, hi = lim
    span = (hi - lo) or 1.0
    if value < lo - span or value > hi + span:
        return "suspect"
    if value < lo:
        return "low"
    if value > hi:
        return "high"
    return "ok"


def signals_for_lid(lid: int) -> "list[Signal]":
    return [s for s in SIGNALS if s.lid == lid]


def decode_lid(lid: int, data: bytes) -> "dict[str, float]":
    """Decode all signals in a LID from its data field (skips those that do not fit)."""
    return {s.name: s.decode(data) for s in signals_for_lid(lid) if s.fits(data)}
