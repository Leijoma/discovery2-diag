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
    # LID 1B: gaspedalgivare (accelerator), 4 fält — svaret är 8 databytes.
    # Två redundanta potentiometerspår, beräknad pedalbegäran (%), 5V-referens.
    Signal("pedal_track1", 0x1B, 0, scale=1 / 1000, unit="V"),
    Signal("pedal_track2", 0x1B, 2, scale=1 / 1000, unit="V"),
    Signal("pedal_demand", 0x1B, 4, scale=1 / 100, unit="%"),
    Signal("pedal_supply", 0x1B, 6, scale=1 / 1000, unit="V"),
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


def signals_for_lid(lid: int) -> "list[Signal]":
    return [s for s in SIGNALS if s.lid == lid]


def decode_lid(lid: int, data: bytes) -> "dict[str, float]":
    """Avkoda alla signaler i en LID ur dess datafält (hoppar över de som inte får plats)."""
    return {s.name: s.decode(data) for s in signals_for_lid(lid) if s.fits(data)}
