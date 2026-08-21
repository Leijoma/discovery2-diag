"""The K-Line layer: fast init, frame I/O, echo handling, timeout and retries.

Sits on top of a :class:`~d2diag.transport.base.Transport` and below KWP2000.
K-Line is half-duplex: every sent byte echoes back and is swallowed before the reply is read.

Td5 flow: ``fast_init()`` sends the *addressed* StartCommunication frame;
after that the session runs with *unaddressed* frames via ``request()``. ``read_frame``
handles both formats automatically (reads the address bits of the format byte).
"""
from __future__ import annotations

import time

from ..transport.base import Transport
from .frame import (
    TD5_ECU_ADDRESS,
    TESTER_ADDRESS,
    ChecksumError,
    DecodedFrame,
    FrameError,
    decode,
    encode,
)

DEFAULT_START_COMMUNICATION = b"\x81"

# ISO 14230-2 fast init: line low 25 ms (TiniL), then high 25 ms, then
# StartCommunication.
_FAST_INIT_LOW = 0.025
_FAST_INIT_HIGH = 0.025


def _precise_wait(seconds: float) -> None:
    """Wait ``seconds`` with sub-millisecond precision.

    ``time.sleep`` overshoots: measured on macOS, ``sleep(25 ms)`` actually
    gives 25.3–32.0 ms (median 29.1). For TiniH, which ISO 14230-2 sets to
    25 ms ± 1, that is too blunt. We therefore sleep only up to 2 ms before the target
    and spin the last bit — 25 ms of burned CPU cycles once per connection attempt
    is a cheap price for a pulse within tolerance.
    """
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    # Coarse sleep only for long waits: a sleep() can overshoot 5–7 ms, so for
    # the init pulse's 25 ms it alone would miss the target. Spin the whole way instead.
    coarse = seconds - 0.050
    if coarse > 0:
        time.sleep(coarse)
    while time.perf_counter() < deadline:
        pass


class KLineError(Exception):
    pass


class KLineTimeout(KLineError):
    pass


class KLine:
    def __init__(
        self,
        transport: Transport,
        target: int = TD5_ECU_ADDRESS,
        source: int = TESTER_ADDRESS,
        timeout: float = 1.0,
        echo: bool = True,
        write_gap: float = 0.0,
        init_low: float = _FAST_INIT_LOW,
        init_high: float = _FAST_INIT_HIGH,
        init_idle: float = 0.0,
    ) -> None:
        self._t = transport
        self._target = target
        self._source = source
        self._timeout = timeout
        self._echo = echo
        # P4 — inter-byte time in the tester's request. ISO 14230-2 specifies 5–20 ms, and
        # the muki01 reference (confirmed correct) sends one byte at a time with 5 ms
        # in between. We have always sent the whole frame in one sweep (~1 ms/byte at
        # 10400 baud), which a strict ECU may refuse to parse. 0.0 = old behaviour.
        self.write_gap = write_gap
        # ISO 14230-2 fast init: TiniL = 25 ms ± 1 low, then 25 ms ± 1 high, then
        # StartCommunication. The low pulse is hardware-timed (baud drop), but the HIGH
        # period is time.sleep() and what happens afterwards — flush + USB write —
        # is outside our control. An FTDI/CH340 also buffers with its
        # latency timer (default 16 ms), so the actual time to the first byte can
        # become 25–45 ms instead of 25. Hence adjustable, and measured: see last_pulse.
        self.init_low = init_low
        self.init_high = init_high
        # W5 — bus-idle before fast init. ISO 14230-2 specifies 300 ms; we had nothing at all.
        # 0.0 = off (old behaviour); set 0.3–1.0 to eliminate W5 as a variable.
        self.init_idle = init_idle
        self.last_pulse: "dict" = {}
        self._rxbuf = bytearray()  # leftover bytes between frames (resync)

    # ---- lifecycle ---------------------------------------------------- #
    def open(self) -> None:
        self._t.open()

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> "KLine":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- init --------------------------------------------------------- #
    def _fast_init_pulse(self) -> None:
        """The physical init pulse: line low ``init_low``, then high ``init_high``.

        Measures what ACTUALLY happened (``last_pulse``) — nominal values say nothing
        about a USB serial port where the driver and OS add their own delay.
        """
        if self.init_idle:
            time.sleep(self.init_idle)   # W5: let the bus stay quiet before the pulse
        t0 = time.perf_counter()
        self._flush_input()
        # Deterministic low pulse: prefer baud drop (0x00 @ ~360 baud) over an
        # OS-timed break, whose length jitters on non-real-time OSes and makes the Td5
        # never enter diag mode (03 7F 81 10 = generalReject).
        already_high = 0.0
        pulse = getattr(self._t, "fast_init_low", None)
        if pulse is not None:
            already_high = pulse(self.init_low) or 0.0
        else:
            send_break = getattr(self._t, "send_break", None)
            if send_break is None:
                raise KLineError(
                    "transport lacks fast_init_low()/send_break() — required for fast init"
                )
            send_break(self.init_low)
        t1 = time.perf_counter()
        # Subtract the time the line has ALREADY been high (the UART stop bit after the pulse
        # byte), otherwise TiniH becomes systematically too long.
        _precise_wait(max(0.0, self.init_high - already_high))
        t2 = time.perf_counter()
        self.last_pulse = {"low_ms": round((t1 - t0) * 1000, 1),
                           "high_ms": round((t2 - t1) * 1000 + already_high * 1000, 1),
                           "pre_high_ms": round(already_high * 1000, 1)}

    def fast_init(self, start_communication: bytes = DEFAULT_START_COMMUNICATION) -> bytes:
        """Run fast init (addressed StartCommunication) and return the reply's
        data field (e.g. key bytes). Strict frame reading."""
        self._fast_init_pulse()
        # No retry: StartCommunication must be sent ONCE. If it succeeds the session
        # opens; a retransmit is then rejected (generalReject "already in session").
        return self.request(start_communication, addressed=True, retries=0)

    def fast_init_tolerant(
        self,
        start_communication: bytes = DEFAULT_START_COMMUNICATION,
        functional: bool = False,
        source: "int | None" = None,
    ) -> bytes:
        """Fast init with tolerant burst reading: search for 0xC1 in the whole reply burst.

        Returns the burst from 0xC1 onward (C1 + key bytes, possibly followed by
        a glitch). Raises :class:`KLineTimeout` if no C1 appears. The point: a
        noise-damaged C1 frame (e.g. ``03 c1 38 0e f8 00``) still CONTAINS 0xC1, so
        we see "session open" on the first attempt and avoid the re-init loop that
        otherwise opens the session repeatedly and locks the ECU (``7F`` generalReject).
        """
        self._fast_init_pulse()
        t_send = time.perf_counter()
        frame = encode(start_communication, self._target,
                       self._source if source is None else source,
                       addressed=True, functional=functional)
        raw = self.converse(start_communication, addressed=True,
                            functional=functional, source=source)
        # to_frame_ms = the time from the end of the pulse until the send ACTUALLY started.
        # (An earlier attempt subtracted send_ms from the whole converse() and therefore measured
        # the burst read — hence the absurd 130–170 ms.)
        start = getattr(self, "_last_send_start", None)
        if start is not None:
            self.last_pulse["to_frame_ms"] = round((start - t_send) * 1000, 2)
        self.last_pulse["send_ms"] = getattr(self, "_last_send_ms", 0.0)
        # SKIP THE ECHO before we search for C1. Half-duplex echoes everything we send, and
        # a FUNCTIONAL frame itself begins with 0xC1 — without this the search finds
        # our own echo and reports "session established" on an empty bus
        # (car 2026-08-19: `C1! c1 29 f1 81` = the echo, the 1A 8A acknowledgement was dropped).
        i = raw.find(frame)
        if i >= 0:
            search, offset = raw[i + len(frame):], i + len(frame)
        elif functional:
            # The echo glitched. Still don't search the first bytes where it was — a
            # 0xC1 there is most likely our own.
            search, offset = raw[len(frame):], len(frame)
        else:
            search, offset = raw, 0   # a physical echo (0x8n) contains no 0xC1
        j = search.find(0xC1)
        if j < 0:
            # Be explicit that the echo is skipped: a functional frame BEGINS with 0xC1,
            # so "no C1 in the burst" read wrong against a burst that appears to start with c1.
            raise KLineTimeout(
                f"no response after the echo (echo {frame.hex(' ')}, "
                f"burst {raw.hex(' ') or 'empty'})")
        return raw[offset + j:]

    def slow_init(self, address: int) -> "tuple[int, int]":
        """5-baud slow init to a module (e.g. SLABS — the engine uses fast init).

        Returns key bytes (KW1, KW2). Raises :class:`KLineTimeout` if no module
        answers (no 0x55 in the reply). Requires the transport to support ``slow_init``.
        """
        slow = getattr(self._t, "slow_init", None)
        parse = getattr(self._t, "parse_slow_init", None)
        if slow is None or parse is None:
            raise KLineError("transporten saknar slow_init()/parse_slow_init()")
        self._flush_input()
        raw = slow(address)
        kw = parse(raw)
        if kw is None:
            raise KLineTimeout(
                f"no slow-init response on 0x{address:02X}: {raw.hex(' ') or 'empty'}"
            )
        return kw

    # ---- request/response --------------------------------------------- #
    def request(self, data: bytes, retries: int = 2, addressed: bool = False) -> bytes:
        """Send a data field, return the reply's data field. Retries on
        timeout or a broken frame. Session traffic is unaddressed (``addressed=False``);
        fast init uses ``addressed=True``."""
        frame = encode(data, self._target, self._source, addressed=addressed)
        last: Exception | None = None
        for _ in range(retries + 1):
            self._flush_input()
            self._send(frame)
            try:
                if self._echo:
                    self.read_frame()  # consume our own echo (first valid frame)
                return self.read_frame().data  # the reply = next valid frame
            except (KLineTimeout, ChecksumError, FrameError) as exc:
                last = exc
        assert last is not None
        raise last

    # ---- tolerant burst I/O (noisy cheap KKL cables) ------------------ #
    def converse(
        self,
        data: bytes,
        addressed: bool = False,
        gap: float = 0.06,
        overall: float = 1.0,
        functional: bool = False,
        source: "int | None" = None,
    ) -> bytes:
        """Send a data field and read the WHOLE reply burst raw (echo + reply +
        any glitch bytes) — without checksum rejection.

        The opposite of :meth:`request`: no frame is validated here. The caller
        searches the burst for the expected reply byte itself. Intended for cheap KKL cables
        where the turnaround glitch shreds individual frames but the right byte is still present.
        """
        frame = encode(data, self._target, self._source if source is None else source,
                       addressed=addressed, functional=functional)
        self._flush_input()
        self._send(frame)
        return self._burst_read(gap, overall)

    def _burst_read(self, gap: float, overall: float) -> bytes:
        """Collect bytes until it goes quiet for ``gap`` s (inter-byte gap), but at most
        ``overall`` s total. muki01 style: read the whole burst, then interpret it."""
        buf = bytearray()
        start = time.monotonic()
        got = False
        while time.monotonic() - start < overall:
            chunk = self._t.receive(64, timeout=gap)
            if chunk:
                buf += chunk
                got = True
            elif got:
                break  # silence after data → the burst is done
            else:
                time.sleep(0.002)  # still waiting for the first byte
        return bytes(buf)

    def _send(self, frame: bytes) -> None:
        """Send a frame, with a P4 gap between bytes if ``write_gap`` is set."""
        t0 = time.perf_counter()
        self._last_send_start = t0
        try:
            self._send_inner(frame)
        finally:
            self._last_send_ms = round((time.perf_counter() - t0) * 1000, 1)

    def _send_inner(self, frame: bytes) -> None:
        if self.write_gap <= 0:
            self._t.send(frame)
            return
        for i, b in enumerate(frame):
            self._t.send(bytes([b]))
            if i + 1 < len(frame):
                _precise_wait(self.write_gap)  # sleep(5 ms) overshoots coarsely

    def read_frame(self, timeout: "float | None" = None) -> DecodedFrame:
        """Read and decode a frame — robust against garbage at the start.

        K-line is half-duplex, and at the turnaround (our TX → the ECU's reply) a
        glitch byte (e.g. 0xF8/0x00) can sneak in before the real frame. Instead
        of strictly interpreting the first byte as the format byte we collect bytes and
        return the first frame with a **valid checksum**. Bytes after the frame (e.g.
        a following reply during responsePending) are saved for the next call.
        """
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        while True:
            frame, consumed = self._scan_for_frame(self._rxbuf)
            if frame is not None:
                del self._rxbuf[:consumed]  # remove any glitch + the frame
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KLineTimeout(
                    f"timeout: no valid frame (buffer: {bytes(self._rxbuf).hex(' ')})"
                )
            chunk = self._t.receive(64, timeout=remaining)
            if chunk:
                self._rxbuf += chunk
            else:
                time.sleep(0.001)

    @staticmethod
    def _scan_for_frame(buf: "bytearray") -> "tuple[DecodedFrame | None, int]":
        """Search for the first valid frame in the buffer. Returns (frame, number of bytes to
        consume up to and including the frame) or (None, 0) if no complete valid frame exists."""
        n = len(buf)
        for start in range(n):
            fmt = buf[start]
            mode = (fmt >> 6) & 0x03
            idx = start + 1
            if mode in (0b10, 0b11):
                idx += 2  # Tgt + Src
            elif mode != 0b00:
                continue  # unsupported address mode — garbage, skip ahead
            length = fmt & 0x3F
            if length == 0:
                if idx >= n:
                    continue
                length = buf[idx]
                idx += 1
            if length < 1:
                continue  # empty frame = false positive in noise, skip
            end = idx + length
            if end + 1 > n:
                continue  # incomplete for this start point
            try:
                return decode(bytes(buf[start : end + 1])), end + 1
            except (FrameError, ChecksumError):
                continue
        return None, 0

    # ---- low level ---------------------------------------------------- #
    def _flush_input(self) -> None:
        self._rxbuf.clear()
        flush = getattr(self._t, "reset_input_buffer", None)
        if flush is not None:
            flush()
