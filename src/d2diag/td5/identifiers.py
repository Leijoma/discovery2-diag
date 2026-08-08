"""Td5 ReadDataByLocalIdentifier (0x21) — kända identifiers och skalning.

Protokollfakta (LID-nummer, byte-offset, skalning) härledda ur referensverktyget
**Ekaitza_Itzali** (EA2EGA). Ingen kod därifrån är kopierad — se
THIRD_PARTY_LICENSES.md. Skalningen bör bekräftas mot bilen; markera osäkerheter.

Varje LID (`21 xx`) returnerar ett datablock; en eller flera signaler avkodas ur
det på givna offset. Offset räknas i **datafältet** (efter positiv SID 0x61 och den
ekade identifieraren), dvs det som :meth:`KWP2000.read_local_identifier` returnerar.
"""
from __future__ import annotations

from dataclasses import dataclass


def _u8(data: bytes, off: int) -> int:
    return data[off]


def _u16(data: bytes, off: int) -> int:
    return (data[off] << 8) | data[off + 1]


def _s16(data: bytes, off: int) -> int:
    v = _u16(data, off)
    return v - 0x10000 if v >= 0x8000 else v  # 16-bit tvåkomplement


_READERS = {"u8": _u8, "u16": _u16, "s16": _s16}
_WIDTH = {"u8": 1, "u16": 2, "s16": 2}


@dataclass(frozen=True)
class Signal:
    name: str
    lid: int
    offset: int
    kind: str = "u16"
    scale: float = 1.0
    bias: float = 0.0
    unit: str = ""

    def decode(self, data: bytes) -> float:
        return _READERS[self.kind](data, self.offset) * self.scale + self.bias

    def fits(self, data: bytes) -> bool:
        return len(data) >= self.offset + _WIDTH[self.kind]


# temp: u16/10 − 273,2 °C  (Kelvin×10)
_TEMP = dict(kind="u16", scale=0.1, bias=-273.2, unit="°C")

SIGNALS = [
    Signal("rpm", 0x09, 0, "u16", unit="rpm"),
    Signal("speed", 0x0D, 0, "u8", unit="km/h"),
    Signal("battery", 0x10, 0, "u16", scale=1 / 1000, unit="V"),
    # LID 1A: fyra temperaturer på JÄMNA offset (0/4/8/12), u16/10−273.2 °C.
    # De udda offseten (2/6/10/14) är råa givarfält, inte temperaturer.
    Signal("coolant_temp", 0x1A, 0, **_TEMP),
    Signal("air_temp", 0x1A, 4, **_TEMP),
    # OBS: omgivningsluftgivaren är inte monterad på denna ECU-variant → ECU:n
    # rapporterar konstant default 0x1088 = 150,0 °C. Ignorera värdet (oansluten).
    Signal("ext_temp", 0x1A, 8, **_TEMP),
    Signal("fuel_temp", 0x1A, 12, **_TEMP),
    # LID 1B: accelerator-pedalgivare, 4 u16-fält (8 databytes). Nanacom visar
    # **Accel. Way 1/2/3 (V) + Accel. Supply (V)** — SNIFFAT 2026-08-08 (session.log).
    # OBS: @4 tolkades tidigare som "demand %"; Nanacoms etikett visar att det är ett
    # tredje SPÄNNINGSspår (0 V med foten av). Skala 1/1000 V; way3-skalan bör
    # bekräftas med ett pedalsvep (var 0 i fångsten så exakt skala ej sedd).
    Signal("accel_way1", 0x1B, 0, scale=1 / 1000, unit="V"),
    Signal("accel_way2", 0x1B, 2, scale=1 / 1000, unit="V"),
    Signal("accel_way3", 0x1B, 4, scale=1 / 1000, unit="V"),
    Signal("accel_supply", 0x1B, 6, scale=1 / 1000, unit="V"),
    # LID 1C@0: grenrörstryck (MAP). BEKRÄFTAT mot bilen 2026-08-03 — steg
    # 1.0→1.2 bar under acceleration. boost = MAP − ambient(23).
    Signal("manifold_press", 0x1C, 0, scale=1 / 10000, unit="bar"),
    # 1C@4: ingen MAF-givare på denna tidiga Td5-ROM → EJ luftmassa (går 50→0
    # av→igång). Behållet som rått fält; tolka inte som mg.
    Signal("maf_raw", 0x1C, 4, "u16", unit=""),
    Signal("rpm_error", 0x21, 0, "s16", unit="rpm"),
    Signal("ambient_press_1", 0x23, 0, scale=1 / 10000, unit="bar"),
    Signal("ambient_press_2", 0x23, 2, scale=1 / 10000, unit="bar"),
    Signal("balance_1", 0x40, 0, "s16"),
    Signal("balance_2", 0x40, 2, "s16"),
    Signal("balance_3", 0x40, 4, "s16"),
    Signal("balance_4", 0x40, 6, "s16"),
    Signal("balance_5", 0x40, 8, "s16"),
]

BY_NAME = {s.name: s for s in SIGNALS}
LIDS = sorted({s.lid for s in SIGNALS})

# Rimliga driftsintervall (min_ok, max_ok) för avvikelseflaggning. Signaler utan
# post flaggas inte (ext_temp = oansluten givare 150 °C; maf_raw = okänd skala).
LIMITS = {
    "rpm": (0, 4800),
    "speed": (0, 200),
    "battery": (11.5, 15.5),
    "coolant_temp": (-40, 105),      # bara högt = överhettning; kallstart lågt är ok
    "air_temp": (-30, 80),
    "fuel_temp": (-30, 90),
    "manifold_press": (0.8, 2.6),
    "ambient_press_1": (0.8, 1.1),
    "ambient_press_2": (0.8, 1.1),
    "rpm_error": (-300, 300),
    "accel_way1": (0.0, 5.1),
    "accel_way2": (0.0, 5.1),
    "accel_way3": (0.0, 5.1),
    "accel_supply": (4.7, 5.3),      # 5V-referens; utanför = matningsproblem
    "balance_1": (-12, 12),
    "balance_2": (-12, 12),
    "balance_3": (-12, 12),
    "balance_4": (-12, 12),
    "balance_5": (-12, 12),
}


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
