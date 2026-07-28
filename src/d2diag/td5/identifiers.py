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
    Signal("coolant_temp", 0x1A, 0, **_TEMP),
    Signal("air_temp", 0x1A, 4, **_TEMP),
    Signal("ext_temp", 0x1A, 8, **_TEMP),
    Signal("fuel_temp", 0x1A, 12, **_TEMP),
    Signal("throttle_p1", 0x1B, 0, scale=1 / 1000, unit="V"),
    Signal("throttle_p2", 0x1B, 2, scale=1 / 1000, unit="V"),
    Signal("throttle_p3", 0x1B, 4, scale=1 / 1000, unit="V"),
    Signal("throttle_p4", 0x1B, 6, scale=1 / 1000, unit="V"),
    Signal("throttle_supply", 0x1B, 8, scale=1 / 1000, unit="V"),
    Signal("aap", 0x1C, 0, scale=1 / 10000, unit="bar"),
    Signal("maf", 0x1C, 4, "u16", unit="mg"),
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
