"""K-Line-lagret: fast init, ram-I/O, eko-hantering, timeout och retries.

Ligger ovanpå en :class:`~d2diag.transport.base.Transport` och under KWP2000.
Känner till ramformat och init-handskakning — men ingenting om KWP2000-tjänster
eller Td5. K-Line är halv-duplex: varje sänd byte ekar tillbaka och sväljs innan
svaret läses.
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

# ISO 14230-2 fast init: linjen låg 25 ms (TiniL), sedan hög 25 ms, sedan
# StartCommunication.
_FAST_INIT_LOW = 0.025
_FAST_INIT_HIGH = 0.025


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
    ) -> None:
        self._t = transport
        self._target = target
        self._source = source
        self._timeout = timeout
        self._echo = echo

    # ---- livscykel ---------------------------------------------------- #
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
    def fast_init(self, start_communication: bytes = DEFAULT_START_COMMUNICATION) -> bytes:
        """Kör fast init och returnerar StartCommunication-svarets datafält."""
        send_break = getattr(self._t, "send_break", None)
        if send_break is None:
            raise KLineError("transporten saknar send_break() — krävs för fast init")
        self._flush_input()
        send_break(_FAST_INIT_LOW)   # K-line låg 25 ms
        time.sleep(_FAST_INIT_HIGH)  # K-line hög 25 ms
        return self.request(start_communication)

    # ---- request/response --------------------------------------------- #
    def request(self, data: bytes, retries: int = 2) -> bytes:
        """Skicka ett datafält, returnera svarets datafält. Försöker om vid
        timeout eller trasig ram."""
        frame = encode(data, self._target, self._source)
        last: Exception | None = None
        for _ in range(retries + 1):
            self._flush_input()
            self._send(frame)
            try:
                return self.read_frame().data
            except (KLineTimeout, ChecksumError, FrameError) as exc:
                last = exc
        assert last is not None
        raise last

    def read_frame(self, timeout: "float | None" = None) -> DecodedFrame:
        """Läs och avkoda en hel ram från transporten."""
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        fmt = self._read_exact(1, deadline)
        parts = bytearray(fmt)
        if ((fmt[0] >> 6) & 0x03) not in (0b10, 0b11):
            raise FrameError(f"ostött adressläge i format 0x{fmt[0]:02X}")
        parts += self._read_exact(2, deadline)  # Tgt + Src
        length = fmt[0] & 0x3F
        if length == 0:
            length_byte = self._read_exact(1, deadline)
            parts += length_byte
            length = length_byte[0]
        parts += self._read_exact(length, deadline)  # data
        parts += self._read_exact(1, deadline)       # checksumma
        return decode(bytes(parts))

    # ---- lågnivå ------------------------------------------------------ #
    def _send(self, frame: bytes) -> None:
        self._t.send(frame)
        if self._echo:
            deadline = time.monotonic() + self._timeout
            echo = self._read_exact(len(frame), deadline)
            if echo != frame:
                raise KLineError(
                    f"eko matchar inte sänt: {echo.hex(' ')} != {frame.hex(' ')}"
                )

    def _read_exact(self, n: int, deadline: float) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KLineTimeout(f"timeout: fick {len(buf)}/{n} bytes")
            chunk = self._t.receive(n - len(buf), timeout=remaining)
            if chunk:
                buf += chunk
            else:
                time.sleep(0.001)  # undvik busy-spin i väntan på bytes
        return bytes(buf)

    def _flush_input(self) -> None:
        flush = getattr(self._t, "reset_input_buffer", None)
        if flush is not None:
            flush()
