"""KWP2000-ramformat på K-Line (ISO 14230-2).

Td5 använder TVÅ ramvarianter:

* **Adresserad** (fast init / StartCommunication): formatbyte 0x8n med mål- och
  källadress — ``81 13 F7 81 0C``.
* **Oadresserad** (hela sessionen efter init): formatbyte 0x0n = bara längd —
  ``02 10 A0 B2``, ``02 27 01 2A``.

Formatbyte: bit 7-6 = adressläge (00 = ingen adress, 10 = fysisk), bit 5-0 =
längd (0 → längden ligger i en separat byte). Checksumma = 8-bitars summa av alla
föregående bytes. Detta lager kan bara koda/avkoda ramar — ingen KWP2000-logik.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

TESTER_ADDRESS = 0xF7
TD5_ECU_ADDRESS = 0x13


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
    addressed: bool = False,
) -> bytes:
    """Bygg en komplett ram med checksumma.

    ``addressed=True`` ger den adresserade init-varianten (0x8n, med tgt/src),
    ``False`` den oadresserade sessionsvarianten (0x0n, bara längd).
    """
    n = len(data)
    if n == 0:
        raise FrameError("tomt datafält")
    if n > 0xFF:
        raise FrameError(f"för långt datafält: {n} bytes")
    if addressed:
        if n <= 0x3F:
            header = bytes([0x80 | n, target, source])
        else:
            header = bytes([0x80, target, source, n])
    else:
        if n <= 0x3F:
            header = bytes([n])
        else:
            header = bytes([0x00, n])
    body = header + bytes(data)
    return body + bytes([checksum(body)])


@dataclass(frozen=True)
class DecodedFrame:
    data: bytes
    target: Optional[int] = None
    source: Optional[int] = None

    @property
    def addressed(self) -> bool:
        return self.target is not None


def decode(frame: bytes) -> DecodedFrame:
    """Avkoda en komplett ram (adresserad eller ej) och verifiera checksumman."""
    if len(frame) < 3:  # minst fmt + 1 data + cs (oadresserad)
        raise FrameError(f"för kort ram: {len(frame)} bytes")
    fmt = frame[0]
    mode = (fmt >> 6) & 0x03
    idx = 1
    target: Optional[int] = None
    source: Optional[int] = None
    if mode in (0b10, 0b11):
        if len(frame) < 5:
            raise FrameError("för kort adresserad ram")
        target = frame[1]
        source = frame[2]
        idx = 3
    elif mode != 0b00:
        raise FrameError(f"ostött adressläge i format 0x{fmt:02X}")
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
        raise ChecksumError(f"checksumma 0x{frame[end]:02X}, väntade 0x{expected:02X}")
    return DecodedFrame(bytes(data), target, source)
