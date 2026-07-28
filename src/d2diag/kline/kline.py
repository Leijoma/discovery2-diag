"""K-Line-lagret: fast init, ram-I/O, eko-hantering, timeout och retries.

Ligger ovanpå en :class:`~d2diag.transport.base.Transport` och under KWP2000.
K-Line är halv-duplex: varje sänd byte ekar tillbaka och sväljs innan svaret läses.

Td5-flödet: ``fast_init()`` skickar den *adresserade* StartCommunication-ramen;
därefter körs sessionen med *oadresserade* ramar via ``request()``. ``read_frame``
hanterar båda formaten automatiskt (avläser formatbytens adressbitar).
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
        self._rxbuf = bytearray()  # kvarvarande bytes mellan ramar (resync)

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
        """Kör fast init (adresserad StartCommunication) och returnerar svarets
        datafält (t.ex. nyckelbytes)."""
        self._flush_input()
        # Deterministisk låg-puls: föredra baud-drop (0x00 @ ~360 baud) framför
        # OS-timad break, vars längd jittrar på icke-realtids-OS och gör att Td5:an
        # aldrig går in i diag-läge (03 7F 81 10 = generalReject).
        pulse = getattr(self._t, "fast_init_low", None)
        if pulse is not None:
            pulse(_FAST_INIT_LOW)
        else:
            send_break = getattr(self._t, "send_break", None)
            if send_break is None:
                raise KLineError(
                    "transporten saknar fast_init_low()/send_break() — krävs för fast init"
                )
            send_break(_FAST_INIT_LOW)
        time.sleep(_FAST_INIT_HIGH)  # K-line hög innan StartCommunication
        # Ingen retry: StartCommunication ska skickas EN gång. Lyckas den öppnas
        # sessionen; en omsändning avvisas då (generalReject "redan i session").
        return self.request(start_communication, addressed=True, retries=0)

    # ---- request/response --------------------------------------------- #
    def request(self, data: bytes, retries: int = 2, addressed: bool = False) -> bytes:
        """Skicka ett datafält, returnera svarets datafält. Försöker om vid
        timeout eller trasig ram. Sessionstrafik är oadresserad (``addressed=False``);
        fast init använder ``addressed=True``."""
        frame = encode(data, self._target, self._source, addressed=addressed)
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
        """Läs och avkoda en ram — robust mot skräp i början.

        K-line är halv-duplex, och vid vändningen (vår TX → ECU:ns svar) kan en
        glitch-byte (t.ex. 0xF8/0x00) smyga in före den riktiga ramen. Istället
        för att strikt tolka första byten som formatbyte samlar vi bytes och
        returnerar första ram med **giltig checksumma**. Bytes efter ramen (t.ex.
        ett efterföljande svar vid responsePending) sparas till nästa anrop.
        """
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        while True:
            frame, consumed = self._scan_for_frame(self._rxbuf)
            if frame is not None:
                del self._rxbuf[:consumed]  # ta bort ev. glitch + ramen
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KLineTimeout(
                    f"timeout: ingen giltig ram (buffert: {bytes(self._rxbuf).hex(' ')})"
                )
            chunk = self._t.receive(64, timeout=remaining)
            if chunk:
                self._rxbuf += chunk
            else:
                time.sleep(0.001)

    @staticmethod
    def _scan_for_frame(buf: "bytearray") -> "tuple[DecodedFrame | None, int]":
        """Sök första giltiga ramen i bufferten. Returnerar (ram, antal bytes att
        förbruka t.o.m. ramen) eller (None, 0) om ingen komplett giltig ram finns."""
        n = len(buf)
        for start in range(n):
            fmt = buf[start]
            mode = (fmt >> 6) & 0x03
            idx = start + 1
            if mode in (0b10, 0b11):
                idx += 2  # Tgt + Src
            elif mode != 0b00:
                continue  # ostött adressläge — skräp, hoppa fram
            length = fmt & 0x3F
            if length == 0:
                if idx >= n:
                    continue
                length = buf[idx]
                idx += 1
            end = idx + length
            if end + 1 > n:
                continue  # ofullständig för den här startpunkten
            try:
                return decode(bytes(buf[start : end + 1])), end + 1
            except (FrameError, ChecksumError):
                continue
        return None, 0

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
        self._rxbuf.clear()
        flush = getattr(self._t, "reset_input_buffer", None)
        if flush is not None:
            flush()
