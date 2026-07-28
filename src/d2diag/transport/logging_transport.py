"""LoggingTransport — dekorerar en annan Transport och loggar all rå TX/RX.

Uppfyller kravet "alla paket skall kunna loggas … sparas till fil". Format:

    2026-07-21T12:00:00.123456Z TX 81 13 F7 81 0C
    2026-07-21T12:00:00.234567Z RX 83 F7 13 C1 EA 8F

Eftersom den själv ÄR en Transport kan vilket högre lager som helst ligga ovanpå
den utan att veta att loggning sker:

    t = LoggingTransport(SerialTransport("/dev/ttyUSB0"), logfile="run.log")
    kwp = KWP2000(t)   # loggas transparent
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import TextIO

from .base import Transport


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _timestamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class LoggingTransport(Transport):
    def __init__(
        self,
        inner: Transport,
        logfile: "str | Path | None" = None,
        echo: bool = False,
    ) -> None:
        self._inner = inner
        self._logpath = Path(logfile) if logfile is not None else None
        self._fh: "TextIO | None" = None
        self._echo = echo

    def open(self) -> None:
        self._inner.open()
        if self._logpath is not None and self._fh is None:
            self._fh = open(self._logpath, "a", buffering=1, encoding="utf-8")
        self._is_open = True

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            self._is_open = False

    def send(self, data: bytes) -> int:
        self._log("TX", data)
        return self._inner.send(data)

    def receive(self, size: int = 1, timeout: "float | None" = None) -> bytes:
        data = self._inner.receive(size, timeout)
        if data:
            self._log("RX", data)
        return data

    def __getattr__(self, name: str):
        # Delegera seriell lågnivåkontroll (send_break, reset_input_buffer,
        # baudrate …) till den inre transporten, så wrappern inte döljer dem
        # för K-Line-lagret. Anropas bara för attribut som inte finns här.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    def _log(self, direction: str, data: bytes) -> None:
        line = f"{_timestamp()} {direction} {_hex(data)}"
        if self._fh is not None:
            self._fh.write(line + "\n")
        if self._echo:
            print(line)
