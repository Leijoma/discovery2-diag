"""SLABS hold: keep ONE SLABS session through a drive and log the ORDER faults appear in.

Why (``references/test_plan.md`` T-23): SLABS refuses a *new* StartCommunication once the car
has moved (proven 2026-08-29 with ESP excursions, ``slabs_protocol.md``). So its current faults
(``21 47``) have never been read while lit. Those are the intermittent "four amigos" that clear
at the next ignition cycle. Whether a session opened at a standstill and kept alive survives
driving is the open question this loop answers. The ESP node has the same mode
(``esp32/kline_node``, "SLABS hold"). This module is the Mac/KKL-cable twin, kept pure so it is
testable against ``FakeKLineEcu``.

Load budget: ONE request per :meth:`SlabsHold.step` (the caller paces it at ~1 Hz), cycling
:data:`PATTERN`. That is far below the ~10 req/s block read that killed a SLABS session after
~15 s (``slabs_protocol.md``).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000Error
from .faults import FAULT_BLOCK_LEN, SLABS_FAULT_BITS
from .slabs import Slabs

WHEEL_SPEEDS_LID = 0x43   # 21 43: four u16le, decoding belagt; scale + wheel order kandidat (T-14)

CUR, KEEPALIVE, AUX = "cur", "3e", "aux"
# At 1 Hz: current faults every 2 s, bare 3E and an AUX read every 4 s.
PATTERN = (CUR, KEEPALIVE, CUR, AUX)
LOG_EVERY = 8     # every 8th AUX slot reads 21 11 (logged) instead of 21 43 (~every 32 s)
STATUS_EVERY = 3  # a status event every 3rd wheel read (~every 12 s)
MISS_MAX = 3      # unanswered requests in a row → the session is gone


@dataclass
class HoldEvent:
    t: float               # wall clock (epoch seconds, sub-second)
    kind: str              # up | down | estab_fail | edge | status
    seq: int = 0           # 21 47 poll counter at the time of the event
    up_s: float = 0.0      # how long the current session has lived
    block: str = ""        # edge: "cur" (21 47) or "log" (21 11)
    bit: str = ""          # edge: "byte.bit"
    state: int = 0         # edge: 1 = set, 0 = cleared
    base: bool = False     # edge: already set when the session came up (onset NOT observed)
    text: str = ""         # decoded fault / detail
    raw: str = ""          # raw block / wheel speeds as hex


def fault_label(byte: int, bit: int) -> str:
    known = SLABS_FAULT_BITS.get((byte, bit))
    return f"{known[0]}: {known[1]}" if known else f"unknown (byte {byte}, bit {bit})"


class SlabsHold:
    """The hold loop. :meth:`connect` once at a standstill, then :meth:`step` ~1 Hz."""

    def __init__(
        self,
        slabs: Slabs,
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        establish: "Callable[[], object] | None" = None,
    ) -> None:
        self._s = slabs
        self._clock = clock
        self._mono = monotonic
        self._establish = establish or slabs.establish
        self.up = False
        self.seq = 0
        self.wheels = b""
        self.lost_after: "float | None" = None
        self._since = 0.0
        self._step = 0
        self._aux = 0
        self._miss = 0
        self._prev: "dict[str, bytes]" = {}

    def up_s(self) -> float:
        return self._mono() - self._since if self.up else 0.0

    def _ev(self, kind: str, **kw) -> HoldEvent:
        return HoldEvent(self._clock(), kind, seq=self.seq, up_s=round(self.up_s(), 1), **kw)

    def connect(self) -> "list[HoldEvent]":
        try:
            self._establish()
        except (KWP2000Error, KLineError) as exc:
            self._s.end_session()  # 82: never leave a half-open link on the shared bus
            return [self._ev("estab_fail", text=str(exc))]
        self.up = True
        self._since = self._mono()
        self._step = 0
        self._aux = LOG_EVERY - 1  # first AUX slot reads 21 11, so the logged baseline comes early
        self._miss = 0
        self._prev = {}
        return [self._ev("up")]

    def _edges(self, block: str, data: bytes) -> "list[HoldEvent]":
        """One event per bit that changed vs the previous read of this block.

        The first read of a session is the baseline: bits already set are reported with
        ``base=True`` so they are never mistaken for an onset that was observed live."""
        if len(data) < FAULT_BLOCK_LEN:
            return []  # a short read is noise, not a fault change (same rule as the ESP node)
        data = bytes(data[:FAULT_BLOCK_LEN])
        prev = self._prev.get(block)
        base = prev is None
        out = []
        for i, now in enumerate(data):
            diff = now if base else now ^ prev[i]
            for b in range(8):
                if diff & (1 << b):
                    out.append(self._ev(
                        "edge", block=block, bit=f"{i}.{b}", state=(now >> b) & 1, base=base,
                        text=fault_label(i, b), raw=data.hex(" ")))
        self._prev[block] = data
        return out

    def _status(self) -> HoldEvent:
        cur = self._prev.get("cur", b"")
        return self._ev("status", raw=self.wheels.hex(" "),
                        text=f"fcur={cur.hex(' ')}" if cur else "")

    def step(self) -> "list[HoldEvent]":
        """Send exactly ONE request. Returns the events it produced (often none)."""
        if not self.up:
            raise RuntimeError("SlabsHold.step() without a session; call connect() first")
        kind = PATTERN[self._step]
        self._step = (self._step + 1) % len(PATTERN)
        events: "list[HoldEvent]" = []
        try:
            if kind == KEEPALIVE:
                self._s.tester_present()          # BARE 3E: `3E 01` kills SLABS' session
            elif kind == CUR:
                self.seq += 1
                events += self._edges("cur", self._s.read_current_faults_raw())
            else:
                self._aux += 1
                if self._aux % LOG_EVERY == 0:
                    events += self._edges("log", self._s.read_logged_faults_raw())
                else:
                    self.wheels = self._s.read_local(WHEEL_SPEEDS_LID)
                    if self._aux % STATUS_EVERY == 1:
                        events.append(self._status())
        except (KWP2000Error, KLineError) as exc:
            self._miss += 1
            if self._miss < MISS_MAX:
                return events
            self.lost_after = round(self.up_s(), 1)
            events.append(self._ev("down", text=str(exc)))   # the moment it died + how long it lived
            self.up = False
            self._s.end_session()
            return events
        self._miss = 0
        return events
