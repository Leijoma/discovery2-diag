"""SerialTransport — bytes over a serial K-Line adapter (USB KKL / FTDI).

This is the *primary* transport. The library runs on the Raspberry Pi where
the KKL cable sits, so the serial port is local and the time-sensitive
K-Line traffic avoids a network hop.

Testing without hardware: use the url ``loop://`` (pyserial's built-in echo port), or
``socket://host:port``. ``serial_for_url`` handles both real ports and
test urls, so the same code is tested and run.
"""
from __future__ import annotations

import sys
import time

import serial  # pyserial

from .base import Transport

# KWP2000 over K-Line runs 10400 baud, 8N1.
DEFAULT_URL = "/dev/ttyUSB0"
DEFAULT_BAUDRATE = 10400


class SerialTransport(Transport):
    def __init__(
        self,
        url: str = DEFAULT_URL,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = 1.0,
    ) -> None:
        self._url = url
        self._baudrate = baudrate
        self._timeout = timeout
        self._ser: "serial.SerialBase | None" = None

    def open(self) -> None:
        if self._is_open:
            return
        self._ser = serial.serial_for_url(
            self._url,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self._timeout,
        )
        self._is_open = True

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None
        self._is_open = False

    def send(self, data: bytes) -> int:
        ser = self._require_open()
        n = ser.write(data)
        ser.flush()
        return n if n is not None else len(data)

    def receive(self, size: int = 1, timeout: float | None = None) -> bytes:
        ser = self._require_open()
        if timeout is not None and timeout != ser.timeout:
            ser.timeout = timeout
        return ser.read(size)

    # ------------------------------------------------------------------ #
    # Serial low-level control that the K-Line layer (next step) needs.
    #
    # The Transport contract is deliberately clean (send/receive only). But K-Line
    # fast init and byte timing require serial-specific tricks — holding
    # the line low, changing the baudrate, flushing buffers. They are exposed HERE and may
    # be used ONLY by the K-Line layer, never by KWP2000/Td5.
    # ------------------------------------------------------------------ #
    @property
    def baudrate(self) -> int:
        return self._ser.baudrate if self._ser is not None else self._baudrate

    @baudrate.setter
    def baudrate(self, value: int) -> None:
        self._baudrate = value
        if self._ser is not None:
            self._ser.baudrate = value

    def send_break(self, duration: float = 0.025) -> None:
        """Hold K-Line low for ``duration`` seconds via a UART break.

        NOTE: the break length is controlled by the OS scheduler and jitters on non-real-time
        OSes. Prefer :meth:`fast_init_low` for a deterministic init pulse.
        """
        ser = self._require_open()
        ser.break_condition = True
        time.sleep(duration)
        ser.break_condition = False

    def fast_init_low(self, low_seconds: float = 0.025) -> float:
        """Deterministic low pulse for ISO 14230 fast init — without an OS-timed break.

        Lower the baudrate and send ONE 0x00 byte: start bit + 8 zeros = 9 low bits
        in a row. The pulse length is set by the UART's bit clock (hardware), not by the OS
        scheduler, so it is stable even over USB. 9 bits / ``low_seconds``
        gives the baudrate (≈360 baud for 25 ms).

        **Returns how long the line has already been HIGH when we return.**
        The UART frame ends with a stop bit, which is high — at 360 baud it is
        ~2.8 ms long, and ``flush()`` waits until it has been sent. TiniH has therefore already
        begun before the caller gets to sleep. Without this compensation the
        real high period becomes 25 + 2.8 ms instead of 25 (pointed out by an external
        review 2026-08-19).
        """
        ser = self._require_open()
        baud = max(1, round(9 / low_seconds))

        # ⚠️ FTDI on LINUX (Raspberry Pi) can't handle a baudrate as low as 360.
        # The kernel/ftdi_sio clamps it, so the 0x00 byte is sent at ~4500 baud and
        # the low pulse becomes only ~2 ms instead of 25 → the ECU never wakes up.
        # Measured in the car 2026-08-21: the baud trick gave low_ms 1.9–2.8 and NEVER C1;
        # the OS-timed break gave low_ms 26 ms and C1 on the first attempt.
        # macOS handles 360 baud fine, so there we keep the deterministic
        # baud pulse (less scheduler jitter). loop:// (test) handles both.
        if sys.platform.startswith("linux"):
            self.send_break(low_seconds)
            return 0.0  # no stop bit to compensate for — the break is pure low time

        original = ser.baudrate
        try:
            ser.baudrate = baud
            ser.write(b"\x00")
            ser.flush()  # block until the byte is physically sent (incl. the stop bit)
        finally:
            ser.baudrate = original
        # Everything FROM HERE is time when the line is already high: the stop bit plus what
        # the baudrate reset and buffer flush cost (measured 10–20 ms over USB).
        # If it's not counted, TiniH becomes systematically too long — and that was exactly
        # what kept us outside the SLABS tolerance window.
        t_high_started = time.perf_counter() - 1.0 / baud
        ser.reset_input_buffer()  # discard the echo of the pulse byte
        return time.perf_counter() - t_high_started

    @staticmethod
    def slow_init_bits(address: int) -> "list[int]":
        """5-baud init frame for ``address``: start bit(0), **8 data bits LSB-first**,
        stop bit(1) — 8N1, no parity (KWP2000 slow init). Pure + testable.

        FIXED 2026-08-04: the previous 7 data bits + a miscalculated "odd parity" gave the wrong
        byte for addresses with an odd number of ones (0x29→0xA9, 0x34→0xB4) — which would have
        made a slow-init scan miss exactly the interesting candidates. 0x33
        happened to come out right and hid the bug."""
        bits = [0]
        for i in range(8):
            bits.append((address >> i) & 1)
        bits.append(1)
        return bits

    @staticmethod
    def parse_slow_init(raw: bytes) -> "tuple[int, int] | None":
        """Pick (KW1, KW2) out of a slow-init reply that starts with 0x55. Pure + testable."""
        if len(raw) >= 3 and raw[0] == 0x55:
            return raw[1], raw[2]
        return None

    def slow_init(
        self,
        address: int,
        bit_seconds: float = 0.2,
        w4: float = 0.03,
        read_timeout: float = 0.5,
    ) -> bytes:
        """ISO 9141 / ISO 14230 **5-baud slow init** — full handshake.

        1. Send the address byte at 5 baud by bit-banging the break condition
           (line low = break on, high = break off; 200 ms/bit; OS timing is good enough).
        2. Read the ECU's ``0x55`` sync + KW1 + KW2 at the regular baud.
        3. Wait W4 and send ``~KW2`` (inverse). 4. Read the ``~address`` confirmation.

        Returns ALL received bytes (sync + key bytes [+ echo + ~address]). Empty
        or without a leading 0x55 = no module answered on the address. Use
        :meth:`parse_slow_init` to pick out KW1/KW2.
        """
        ser = self._require_open()
        bits = self.slow_init_bits(address)
        ser.break_condition = False  # line idle (high) before start
        ser.reset_input_buffer()
        time.sleep(bit_seconds)
        for bit in bits:
            ser.break_condition = bit == 0  # 0 → break (low), 1 → idle (high)
            time.sleep(bit_seconds)
        ser.break_condition = False  # back to idle
        ser.reset_input_buffer()  # discard RX garbage from our own bit-bang
        ser.timeout = read_timeout
        got = bytearray(ser.read(3))  # 0x55, KW1, KW2
        if len(got) >= 3 and got[0] == 0x55:
            kw2 = got[2]
            time.sleep(w4)
            ser.reset_input_buffer()
            ser.write(bytes([(~kw2) & 0xFF]))  # ~KW2 back to the ECU
            ser.flush()
            got += ser.read(3)  # half-duplex echo + ~address confirmation
        return bytes(got)

    def reset_input_buffer(self) -> None:
        self._require_open().reset_input_buffer()

    def _require_open(self) -> "serial.SerialBase":
        if not self._is_open or self._ser is None:
            raise RuntimeError("SerialTransport is not open — call open() first")
        return self._ser
