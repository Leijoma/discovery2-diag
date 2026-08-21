"""The transport layer — a raw byte pipe.

This layer knows NOTHING about K-Line, KWP2000 or Td5. The only thing it does is
move bytes back and forth. Everything above (K-Line → KWP2000 → Td5) is built against
this interface and does not care whether the transport is serial, TCP or something
else.

    transport = SerialTransport("/dev/ttyUSB0")   # or TcpTransport(...), later
    kwp = KWP2000(transport)                       # next layer, knows only Transport
"""
from __future__ import annotations

import abc


class Transport(abc.ABC):
    """Abstract base. The only contract is send/receive plus open/close."""

    _is_open: bool = False

    @abc.abstractmethod
    def open(self) -> None:
        """Open the channel. Idempotent — may be called on an already-open transport."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the channel. Idempotent."""

    @abc.abstractmethod
    def send(self, data: bytes) -> int:
        """Send raw bytes. Returns the number of bytes written."""

    @abc.abstractmethod
    def receive(self, size: int = 1, timeout: float | None = None) -> bytes:
        """Read up to ``size`` bytes.

        Blocks at most ``timeout`` seconds (``None`` = the transport's default).
        May return fewer than ``size`` bytes, or ``b""`` on timeout.
        """

    @property
    def is_open(self) -> bool:
        return self._is_open

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
