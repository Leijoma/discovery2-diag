"""Passiv sniff-feed för Mappning-/Karta-fliken.

En bakgrundstråd matar en :class:`~d2diag.sniff.decoder.LidStore` med rader från
antingen en riktig ESP32-serieport (live, RX-only) eller en uppspelad loggfil
(för utveckling/demo utan bil). Webbservern läser ``snapshot()`` — som även bär
**färskhet** (ramar/s, ålder på senaste ram, status) så gränssnittet kan visa om
det verkligen är live-data eller en död/stillastående port.
"""
from __future__ import annotations

import threading
import time

from ..sniff.decoder import LidStore, parse_hex_line


class SnifferFeed:
    def __init__(self, lines_factory, delay: float = 0.0, loop: bool = False,
                 source: str = "") -> None:
        self.store = LidStore()
        self._factory = lines_factory  # callable → iterator[str]
        self._delay = delay
        self._loop = loop
        self.source = source
        self.status = "startar"      # startar | live | tom | fel
        self.error: "str | None" = None
        self.lines = 0               # all bustrafik (inkl. keepalives) — heartbeat
        self._last_activity: "float | None" = None
        self._stop = threading.Event()
        self._thread: "threading.Thread | None" = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                for line in self._factory():
                    if self._stop.is_set():
                        return
                    b = parse_hex_line(line)
                    if b:  # NÅGON bustrafik (även keepalive) = levande buss
                        self.lines += 1
                        self._last_activity = time.monotonic()
                        self.status = "live"
                        self.store.ingest_bytes(b)
                    if self._delay:
                        self._stop.wait(self._delay)
            except Exception as exc:  # noqa: BLE001 — t.ex. seriell frånkoppling
                self.status = "fel"
                self.error = f"{type(exc).__name__}: {exc}"
                self._stop.wait(2.0)  # backa av, försök återansluta
                continue
            # factory tog slut (t.ex. filuppspelning klar)
            if not self._loop:
                if self.status == "startar":
                    self.status = "tom"
                return

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self, module: "str | None" = None) -> "dict":
        snap = self.store.snapshot(module)
        age = None
        if self._last_activity is not None:
            age = round(time.monotonic() - self._last_activity, 1)
        snap.update({
            "status": self.status, "error": self.error, "source": self.source,
            "frames": self.store.frames, "lines": self.lines, "age": age,
        })
        return snap

    # ---- konstruktorer ------------------------------------------------- #
    @classmethod
    def from_file(cls, path: str, delay: float = 0.003, loop: bool = True) -> "SnifferFeed":
        """Spela upp en sniff-logg (för att testa vyn utan bil)."""
        def factory():
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield from fh
        return cls(factory, delay=delay, loop=loop, source=f"replay:{path}")

    @classmethod
    def from_serial(cls, port: str, baud: int = 115200) -> "SnifferFeed":
        """Live från ESP32-sniffern (kline_sniff.ino) — RX-only, sänder aldrig.

        Öppnar porten på nytt vid frånkoppling (``_run`` fångar och återförsöker)."""
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
        return cls(factory, delay=0.0, loop=False, source=f"serial:{port}")
