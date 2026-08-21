"""LoggingTransport — decorates another Transport and logs all raw TX/RX.

Fulfils the requirement "all packets shall be loggable … saved to file". Format:

    2026-07-21T12:00:00.123456Z TX 81 13 F7 81 0C
    2026-07-21T12:00:00.234567Z RX 83 F7 13 C1 EA 8F

Since it IS itself a Transport, any higher layer can sit on top of
it without knowing that logging happens:

    t = LoggingTransport(SerialTransport("/dev/ttyUSB0"), logfile="run.log")
    kwp = KWP2000(t)   # logged transparently
"""
from __future__ import annotations

import datetime as _dt
import os
import time
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
        # Raw log on the Raspberry Pi in the car: power can be cut abruptly (engine off).
        # buffering=1 leaves lines in the OS cache → lost + risk of SD corruption.
        # We therefore fsync to the card at regular intervals (not per line — that causes
        # unnecessary SD wear at ~20–40 writes/s). Bounded: at most ~interval s of loss.
        self._fsync_interval = 2.0
        self._last_fsync = 0.0

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
                try:
                    self._fh.flush()
                    os.fsync(self._fh.fileno())
                except OSError:
                    pass
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
        # Delegate serial low-level control (send_break, reset_input_buffer,
        # baudrate …) to the inner transport, so the wrapper doesn't hide them
        # from the K-Line layer. Called only for attributes that don't exist here.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    def _log(self, direction: str, data: bytes) -> None:
        line = f"{_timestamp()} {direction} {_hex(data)}"
        if self._fh is not None:
            self._fh.write(line + "\n")
            now = time.monotonic()
            if now - self._last_fsync >= self._fsync_interval:
                self._fh.flush()
                try:
                    os.fsync(self._fh.fileno())  # force it down to the SD card
                except OSError:
                    pass
                self._last_fsync = now
        if self._echo:
            print(line)
