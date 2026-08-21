"""Passive sniff feed for the Mapping/Map tab.

A background thread feeds a :class:`~d2diag.sniff.decoder.LidStore` with lines from
either a real ESP32 serial port (live, RX-only) or a replayed log file (for
development/demo without a car). The web server reads ``snapshot()`` — which also
carries **freshness** (frames/s, age of the last frame, status) so the interface can
show whether it's really live data or a dead/stationary port.
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
        self.status = "starting"     # starting | live | empty | error
        self.error: "str | None" = None
        self.lines = 0               # all bus traffic (incl. keepalives) — heartbeat
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
                    if b:  # ANY bus traffic (even keepalive) = live bus
                        self.lines += 1
                        self._last_activity = time.monotonic()
                        self.status = "live"
                        self.store.ingest_bytes(b)
                    if self._delay:
                        self._stop.wait(self._delay)
            except Exception as exc:  # noqa: BLE001 — e.g. serial disconnect
                self.status = "error"
                self.error = f"{type(exc).__name__}: {exc}"
                self._stop.wait(2.0)  # back off, try to reconnect
                continue
            # the factory ran out (e.g. file replay finished)
            if not self._loop:
                if self.status == "starting":
                    self.status = "empty"
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

    # ---- constructors -------------------------------------------------- #
    @classmethod
    def from_file(cls, path: str, delay: float = 0.003, loop: bool = True) -> "SnifferFeed":
        """Replay a sniff log (to test the view without a car)."""
        def factory():
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield from fh
        return cls(factory, delay=delay, loop=loop, source=f"replay:{path}")

    @classmethod
    def from_serial(cls, port: str, baud: int = 115200) -> "SnifferFeed":
        """Live from the ESP32 sniffer (kline_sniff.ino) — RX-only, never transmits.

        Reopens the port on disconnect (``_run`` catches and retries)."""
        def factory():
            import serial  # local so mock/replay work without pyserial
            ser = serial.serial_for_url(port, baudrate=baud, timeout=0.2)
            try:
                while True:
                    raw = ser.readline()
                    if raw:
                        yield raw.decode("ascii", "replace")
            finally:
                ser.close()
        return cls(factory, delay=0.0, loop=False, source=f"serial:{port}")
