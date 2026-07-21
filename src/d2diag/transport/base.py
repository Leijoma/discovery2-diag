"""Transportlagret — en rå byte-pipe.

Detta lager vet INGENTING om K-Line, KWP2000 eller Td5. Det enda det gör är att
flytta bytes fram och tillbaka. Allt ovanför (K-Line → KWP2000 → Td5) byggs mot
detta gränssnitt och bryr sig inte om transporten är seriell, TCP eller något
annat.

    transport = SerialTransport("/dev/ttyUSB0")   # eller TcpTransport(...), senare
    kwp = KWP2000(transport)                       # nästa lager, känner bara Transport
"""
from __future__ import annotations

import abc


class Transport(abc.ABC):
    """Abstrakt bas. Enda kontraktet är send/receive plus öppna/stäng."""

    _is_open: bool = False

    @abc.abstractmethod
    def open(self) -> None:
        """Öppna kanalen. Idempotent — får anropas på en redan öppen transport."""

    @abc.abstractmethod
    def close(self) -> None:
        """Stäng kanalen. Idempotent."""

    @abc.abstractmethod
    def send(self, data: bytes) -> int:
        """Skicka rå bytes. Returnerar antal skrivna bytes."""

    @abc.abstractmethod
    def receive(self, size: int = 1, timeout: float | None = None) -> bytes:
        """Läs upp till ``size`` bytes.

        Blockerar högst ``timeout`` sekunder (``None`` = transportens default).
        Kan returnera färre än ``size`` bytes, eller ``b""`` vid timeout.
        """

    @property
    def is_open(self) -> bool:
        return self._is_open

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
