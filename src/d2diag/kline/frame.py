"""KWP2000 frame format on K-Line (ISO 14230-2).

Td5 uses TWO frame variants:

* **Addressed** (fast init / StartCommunication): format byte 0x8n with target and
  source address — ``81 13 F7 81 0C``.
* **Unaddressed** (the whole session after init): format byte 0x0n = length only —
  ``02 10 A0 B2``, ``02 27 01 2A``.

Format byte: bits 7-6 = address mode (00 = no address, 10 = physical), bits 5-0 =
length (0 → the length is in a separate byte). Checksum = 8-bit sum of all
preceding bytes. This layer can only encode/decode frames — no KWP2000 logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

TESTER_ADDRESS = 0xF7
TD5_ECU_ADDRESS = 0x13


class FrameError(Exception):
    """Broken or unsupported frame."""


class ChecksumError(FrameError):
    """The checksum does not match."""


def checksum(data: bytes) -> int:
    """8-bit sum of all bytes."""
    return sum(data) & 0xFF


def encode(
    data: bytes,
    target: int = TD5_ECU_ADDRESS,
    source: int = TESTER_ADDRESS,
    addressed: bool = False,
    functional: bool = False,
) -> bytes:
    """Build a complete frame with checksum.

    ``addressed=True`` gives the addressed init variant (0x8n, with tgt/src),
    ``False`` the unaddressed session variant (0x0n, length only).

    ``functional=True`` sets the address mode to **functional** (0xCn) instead
    of physical (0x8n). That is the mode the muki01 reference uses
    (``C1 33 F1 81 66``), and the only mode SLABS answered to in our own
    address hunt 2026-08-05 (``C1 29 F1 81 5c`` → `C1 57 8F`, while physical init to
    the same address was silent).
    """
    n = len(data)
    if n == 0:
        raise FrameError("empty data field")
    if n > 0xFF:
        raise FrameError(f"data field too long: {n} bytes")
    if addressed:
        mode = 0xC0 if functional else 0x80
        if n <= 0x3F:
            header = bytes([mode | n, target, source])
        else:
            header = bytes([mode, target, source, n])
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
    """Decode a complete frame (addressed or not) and verify the checksum."""
    if len(frame) < 3:  # at least fmt + 1 data + cs (unaddressed)
        raise FrameError(f"frame too short: {len(frame)} bytes")
    fmt = frame[0]
    mode = (fmt >> 6) & 0x03
    idx = 1
    target: Optional[int] = None
    source: Optional[int] = None
    if mode in (0b10, 0b11):
        if len(frame) < 5:
            raise FrameError("addressed frame too short")
        target = frame[1]
        source = frame[2]
        idx = 3
    elif mode != 0b00:
        raise FrameError(f"unsupported address mode in format 0x{fmt:02X}")
    length = fmt & 0x3F
    if length == 0:
        length = frame[idx]
        idx += 1
    end = idx + length
    if end + 1 > len(frame):
        raise FrameError("frame is shorter than the length field indicates")
    data = frame[idx:end]
    expected = checksum(frame[:end])
    if frame[end] != expected:
        raise ChecksumError(f"checksum 0x{frame[end]:02X}, expected 0x{expected:02X}")
    return DecodedFrame(bytes(data), target, source)
