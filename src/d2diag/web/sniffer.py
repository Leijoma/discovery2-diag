"""Passiv sniff-feed för Mappning-fliken.

En bakgrundstråd matar en :class:`~d2diag.sniff.decoder.LidStore` med rader från
antingen en riktig ESP32-serieport (live, RX-only) eller en uppspelad loggfil
(för utveckling/demo utan bil). Webbservern läser ``snapshot()``.
"""
from __future__ import annotations

import threading

from ..sniff.decoder import LidStore


class SnifferFeed:
    def __init__(self, lines_factory, delay: float = 0.0, loop: bool = False) -> None:
        self.store = LidStore()
        self._factory = lines_factory  # callable → iterator[str]
        self._delay = delay
        self._loop = loop
        self._stop = threading.Event()
        self._thread: "threading.Thread | None" = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            for line in self._factory():
                if self._stop.is_set():
                    break
                self.store.ingest_line(line)
                if self._delay:
                    self._stop.wait(self._delay)
            if not self._loop:
                break

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self, module: "str | None" = None) -> "dict":
        return self.store.snapshot(module)

    # ---- konstruktorer ------------------------------------------------- #
    @classmethod
    def from_file(cls, path: str, delay: float = 0.003, loop: bool = True) -> "SnifferFeed":
        """Spela upp en sniff-logg (för att testa Mappning-vyn utan bil)."""
        def factory():
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield from fh
        return cls(factory, delay=delay, loop=loop)

    @classmethod
    def from_serial(cls, port: str, baud: int = 115200) -> "SnifferFeed":
        """Live från ESP32-sniffern (kline_sniff.ino) — RX-only, sänder aldrig."""
        def factory():
            import serial  # lokalt så mock/replay funkar utan pyserial
            ser = serial.serial_for_url(port, baudrate=baud, timeout=0.2)
            try:
                while True:
                    raw = ser.readline()
                    if raw:
                        yield raw.decode("ascii", "replace")
            finally:
                ser.close()
        return cls(factory, delay=0.0, loop=False)
