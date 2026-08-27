"""EspTransport — use an ESP32 K-line bridge (esp32/kline_bridge) as a Transport.

The ESP becomes "just another cable": it does the timing-critical fast-init pulse LOCALLY
and relays raw bytes to/from K-line over a simple USB-serial line protocol, so the whole
stack (`KLine`→`KWP2000`→`Td5`/`faultscan`/`verify_ecu`) runs over it exactly as over a KKL
cable — which frees the KKL cable to lend to a community tester.

Line protocol (see `esp32/kline_bridge/kline_bridge.ino`):
    PING -> PONG ; INIT [hex] -> OK|"RX hex" ; TX hex -> "RX hex" ; STOP -> OK

Mapping onto the `Transport` contract: `KLine.fast_init` calls `fast_init_low()` then
`converse()` = `send(frame)` + a `receive()` loop. The pulse and the StartCommunication frame
must stay tight (a USB round-trip between them would miss the fast-init window), so
`fast_init_low()` DEFERS the pulse and the next `send()` is fused into one atomic
`INIT <frame>` command — the ESP runs pulse + write + burst-read back-to-back. `send()`
buffers the returned burst; `receive()` drains it.
"""
from __future__ import annotations

import time

from .base import Transport


class EspTransport(Transport):
    """A `Transport` backed by the ESP32 K-line bridge over USB (or any serial link)."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0,
                 boot_wait: float = 2.0) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout          # readline() ceiling: an INIT does ~0.35 s pulse + burst
        self._boot_wait = boot_wait      # the ESP resets on port open (DTR) — wait for its banner
        self._ser = None
        self._rx = bytearray()           # burst buffered from the last send()
        self._init_pending = False       # next send() must fuse with the fast-init pulse

    def open(self) -> None:
        import serial  # lazy (pyserial), like SerialTransport
        if self._ser is None:
            self._ser = serial.Serial(self._port, self._baudrate, timeout=self._timeout)
            time.sleep(self._boot_wait)
            self._ser.reset_input_buffer()
        self._is_open = True

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None
        self._is_open = False

    # ---- line protocol ----------------------------------------------------- #
    def _cmd(self, line: str) -> str:
        """Send one command line, return the ESP's reply (first non-empty line)."""
        self._ser.reset_input_buffer()
        self._ser.write((line + "\n").encode())
        self._ser.flush()
        for _ in range(4):               # skip a stray banner line on the first command
            reply = self._ser.readline().decode(errors="replace").strip()
            if reply:
                return reply
        return ""

    def _buffer_rx(self, reply: str) -> None:
        self._rx.clear()
        if reply.startswith("RX"):
            for tok in reply[2:].split():
                try:
                    self._rx.append(int(tok, 16))
                except ValueError:
                    pass

    # ---- Transport contract ------------------------------------------------ #
    def send(self, data: bytes) -> int:
        hexs = data.hex(" ").upper()   # uppercase to match the bridge's RX output (it parses both)
        if self._init_pending:
            self._init_pending = False
            reply = self._cmd("INIT " + hexs)   # pulse + this frame, atomically
        else:
            reply = self._cmd("TX " + hexs)
        self._buffer_rx(reply)
        return len(data)

    def receive(self, size: int = 1, timeout: "float | None" = None) -> bytes:
        if not self._rx:
            return b""
        n = min(size, len(self._rx))
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    # ---- K-line init hook (KLine.fast_init prefers this over send_break) ---- #
    def fast_init_low(self, low_seconds: float = 0.025) -> float:
        # Defer: fuse the pulse with the StartCommunication frame the next send() carries.
        # Returns 0.0 — no host-side high time to compensate (the ESP owns the pulse).
        self._init_pending = True
        self._rx.clear()
        return 0.0

    def reset_input_buffer(self) -> None:
        self._rx.clear()
        if self._ser is not None:
            self._ser.reset_input_buffer()

    # ---- convenience ------------------------------------------------------- #
    def ping(self) -> bool:
        """True if the bridge answers PING with PONG (probe the port/firmware)."""
        return self._cmd("PING") == "PONG"
