"""SerialTransport — bytes över en seriell K-Line-adapter (USB KKL / FTDI).

Detta är den *primära* transporten. Biblioteket körs på Raspberry Pi:n där
KKL-kabeln sitter, så den seriella porten är lokal och den tidskänsliga
K-Line-trafiken slipper ett nätverkshopp.

Test utan hårdvara: använd url ``loop://`` (pyserials inbyggda ekoport), eller
``socket://host:port``. ``serial_for_url`` hanterar både riktiga portar och
test-url:er, så samma kod testas och körs.
"""
from __future__ import annotations

import time

import serial  # pyserial

from .base import Transport

# KWP2000 över K-Line kör 10400 baud, 8N1.
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
    # Seriell lågnivåkontroll som K-Line-lagret (nästa steg) behöver.
    #
    # Transport-kontraktet är medvetet rent (bara send/receive). Men K-Line
    # fast init och byte-timing kräver seriellt specifika grepp — att hålla
    # linjen låg, byta baudrate, tömma buffertar. De exponeras HÄR och får
    # användas ENBART av K-Line-lagret, aldrig av KWP2000/Td5.
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
        """Håll K-Line låg i ``duration`` sekunder via UART-break.

        OBS: break-längden styrs av OS-schemaläggaren och jittrar på icke-realtids-
        OS. Föredra :meth:`fast_init_low` för deterministisk init-puls.
        """
        ser = self._require_open()
        ser.break_condition = True
        time.sleep(duration)
        ser.break_condition = False

    def fast_init_low(self, low_seconds: float = 0.025) -> None:
        """Deterministisk låg-puls för ISO 14230 fast init — utan OS-timad break.

        Sänk baudraten och skicka EN 0x00-byte: startbit + 8 nollor = 9 låga bitar
        i rad. Pulslängden bestäms av UART:ens bitklocka (hårdvara), inte av OS:ets
        schemaläggare, så den är stabil även över USB. 9 bitar / ``low_seconds``
        ger baudraten (≈360 baud för 25 ms).
        """
        ser = self._require_open()
        baud = max(1, round(9 / low_seconds))
        original = ser.baudrate
        try:
            ser.baudrate = baud
            ser.write(b"\x00")
            ser.flush()  # blockera tills byten är fysiskt utsänd
        finally:
            ser.baudrate = original
        ser.reset_input_buffer()  # kasta ekot av puls-byten

    @staticmethod
    def slow_init_bits(address: int) -> "list[int]":
        """5-baud init-ram för ``address``: startbit(0), 7 databitar LSB-först,
        udda paritet, stoppbit(1). Ren funktion → testbar utan hårdvara."""
        bits = [0]
        parity = 1  # udda paritet
        for i in range(7):
            b = (address >> i) & 1
            bits.append(b)
            parity ^= b
        bits.append(1 if parity == 0 else 0)
        bits.append(1)
        return bits

    def slow_init(self, address: int, bit_seconds: float = 0.2, read_timeout: float = 0.6) -> bytes:
        """ISO 9141 / ISO 14230 **5-baud slow init**.

        Skickar adressbyten vid 5 baud genom att bit-banga break-villkoret
        (linjen låg = break på, hög = break av; 200 ms/bit). OS-timing duger på
        200 ms-nivå. Läser sedan ECU:ns svar (0x55 + keybytes) vid ordinarie baud.
        Returnerar de råa svarsbytesen (tomt = ingen modul svarade på adressen).
        """
        ser = self._require_open()
        bits = self.slow_init_bits(address)
        ser.break_condition = False  # linjen idle (hög) före start
        ser.reset_input_buffer()
        time.sleep(bit_seconds)
        for bit in bits:
            ser.break_condition = bit == 0  # 0 → break (låg), 1 → idle (hög)
            time.sleep(bit_seconds)
        ser.break_condition = False  # tillbaka till idle
        ser.reset_input_buffer()  # kasta RX-skräp från vår egen bit-bang
        ser.timeout = read_timeout
        return ser.read(16)

    def reset_input_buffer(self) -> None:
        self._require_open().reset_input_buffer()

    def _require_open(self) -> "serial.SerialBase":
        if not self._is_open or self._ser is None:
            raise RuntimeError("SerialTransport är inte öppen — anropa open() först")
        return self._ser
