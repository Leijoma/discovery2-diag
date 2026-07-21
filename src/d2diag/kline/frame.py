"""KWP2000-ramformat på K-Line (ISO 14230-2).

En ram:

    [Fmt] [Tgt] [Src] ([Len]) [Data ...] [CS]

* ``Fmt`` — formatbyte. Bit 7-6 = adressläge (10 = fysisk adressering, vilket Td5
  använder), bit 5-0 = längd. Är längden 0 ligger den i en separat ``Len``-byte.
* ``Tgt`` / ``Src`` — mål- och källadress (0x13 = Td5-motorstyrdon, 0xF7 = tester).
* ``CS`` — checksumma = 8-bitars summa av alla föregående bytes.

Detta lager kan bara koda/avkoda ramar och räkna checksummor — ingen KWP2000-
eller Td5-logik.
"""
from __future__ import annotations

from dataclasses import dataclass

TESTER_ADDRESS = 0xF7
TD5_ECU_ADDRESS = 0x13

_ADDRESSED_MODES = (0b10, 0b11)  # fysisk resp. funktionell adressering


class FrameError(Exception):
    """Trasig eller ostödd ram."""


class ChecksumError(FrameError):
    """Checksumman stämmer inte."""


def checksum(data: bytes) -> int:
    """8-bitars summa av alla bytes."""
    return sum(data) & 0xFF


def encode(
    data: bytes,
    target: int = TD5_ECU_ADDRESS,
    source: int = TESTER_ADDRESS,
) -> bytes:
    """Bygg en komplett ram (med adresser, fysisk adressering) och checksumma."""
    n = len(data)
    if n == 0:
        raise FrameError("tomt datafält")
    if n > 0xFF:
        raise FrameError(f"för långt datafält: {n} bytes")
    if n <= 0x3F:
        header = bytes([0x80 | n, target, source])
    else:
        header = bytes([0x80, target, source, n])  # längd i separat byte
    body = header + bytes(data)
    return body + bytes([checksum(body)])


@dataclass(frozen=True)
class DecodedFrame:
    target: int
    source: int
    data: bytes


def decode(frame: bytes) -> DecodedFrame:
    """Avkoda en komplett ram och verifiera checksumman."""
    if len(frame) < 5:  # minst Fmt+Tgt+Src+1 data+CS
        raise FrameError(f"för kort ram: {len(frame)} bytes")
    fmt = frame[0]
    if ((fmt >> 6) & 0x03) not in _ADDRESSED_MODES:
        raise FrameError(f"ostött adressläge i format 0x{fmt:02X}")
    target = frame[1]
    source = frame[2]
    idx = 3
    length = fmt & 0x3F
    if length == 0:
        length = frame[idx]
        idx += 1
    end = idx + length
    if end + 1 > len(frame):
        raise FrameError("ramen är kortare än längdfältet anger")
    data = frame[idx:end]
    expected = checksum(frame[:end])
    if frame[end] != expected:
        raise ChecksumError(
            f"checksumma 0x{frame[end]:02X}, väntade 0x{expected:02X}"
        )
    return DecodedFrame(target, source, bytes(data))
