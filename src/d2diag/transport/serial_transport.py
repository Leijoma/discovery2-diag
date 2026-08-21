"""SerialTransport — bytes över en seriell K-Line-adapter (USB KKL / FTDI).

Detta är den *primära* transporten. Biblioteket körs på Raspberry Pi:n där
KKL-kabeln sitter, så den seriella porten är lokal och den tidskänsliga
K-Line-trafiken slipper ett nätverkshopp.

Test utan hårdvara: använd url ``loop://`` (pyserials inbyggda ekoport), eller
``socket://host:port``. ``serial_for_url`` hanterar både riktiga portar och
test-url:er, så samma kod testas och körs.
"""
from __future__ import annotations

import sys
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

    def fast_init_low(self, low_seconds: float = 0.025) -> float:
        """Deterministisk låg-puls för ISO 14230 fast init — utan OS-timad break.

        Sänk baudraten och skicka EN 0x00-byte: startbit + 8 nollor = 9 låga bitar
        i rad. Pulslängden bestäms av UART:ens bitklocka (hårdvara), inte av OS:ets
        schemaläggare, så den är stabil även över USB. 9 bitar / ``low_seconds``
        ger baudraten (≈360 baud för 25 ms).

        **Returnerar hur länge linjen redan varit HÖG när vi kommer tillbaka.**
        UART-ramen avslutas med en stoppbit, som är hög — vid 360 baud är den
        ~2,8 ms lång, och ``flush()`` väntar tills den sänts. TiniH har alltså redan
        börjat innan anroparen hinner sova. Utan den här kompensationen blir den
        verkliga höga perioden 25 + 2,8 ms i stället för 25 (påpekat av extern
        granskning 2026-08-19).
        """
        ser = self._require_open()
        baud = max(1, round(9 / low_seconds))

        # ⚠️ FTDI på LINUX (Raspberry Pi) klarar inte en så låg baudrate som 360.
        # Kärnan/ftdi_sio klampar den, så 0x00-byten skickas på ~4500 baud och
        # låg-pulsen blir bara ~2 ms i stället för 25 → ECU:n vaknar aldrig.
        # Mätt i bilen 2026-08-21: baud-tricket gav low_ms 1.9–2.8 och ALDRIG C1;
        # den OS-timade breaken gav low_ms 26 ms och C1 på första försöket.
        # macOS klarar 360 baud fint, så där behåller vi den deterministiska
        # baud-pulsen (mindre schemaläggar-jitter). loop:// (test) klarar båda.
        if sys.platform.startswith("linux"):
            self.send_break(low_seconds)
            return 0.0  # ingen stoppbit att kompensera för — breaken är ren låg tid

        original = ser.baudrate
        try:
            ser.baudrate = baud
            ser.write(b"\x00")
            ser.flush()  # blockera tills byten är fysiskt utsänd (inkl. stoppbiten)
        finally:
            ser.baudrate = original
        # Allt HÄRIFRÅN är tid då linjen redan är hög: stoppbiten plus det som
        # baudrate-återställning och buffertrensning kostar (mätt 10–20 ms över USB).
        # Räknas det inte med blir TiniH systematiskt för lång — och det var precis
        # vad som höll oss utanför SLABS toleransfönster.
        t_high_started = time.perf_counter() - 1.0 / baud
        ser.reset_input_buffer()  # kasta ekot av puls-byten
        return time.perf_counter() - t_high_started

    @staticmethod
    def slow_init_bits(address: int) -> "list[int]":
        """5-baud init-ram för ``address``: startbit(0), **8 databitar LSB-först**,
        stoppbit(1) — 8N1, ingen paritet (KWP2000 slow init). Ren + testbar.

        RÄTTAT 2026-08-04: tidigare 7 databitar + felräknad "udda paritet" gav fel
        byte för adresser med udda antal ettor (0x29→0xA9, 0x34→0xB4) — vilket hade
        fått en slow-init-skanning att missa just de intressanta kandidaterna. 0x33
        råkade bli rätt och dolde buggen."""
        bits = [0]
        for i in range(8):
            bits.append((address >> i) & 1)
        bits.append(1)
        return bits

    @staticmethod
    def parse_slow_init(raw: bytes) -> "tuple[int, int] | None":
        """Plocka (KW1, KW2) ur ett slow-init-svar som börjar med 0x55. Ren + testbar."""
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
        """ISO 9141 / ISO 14230 **5-baud slow init** — full handskakning.

        1. Skicka adressbyten vid 5 baud genom att bit-banga break-villkoret
           (linjen låg = break på, hög = break av; 200 ms/bit; OS-timing duger).
        2. Läs ECU:ns ``0x55`` sync + KW1 + KW2 vid ordinarie baud.
        3. Vänta W4 och skicka ``~KW2`` (invers). 4. Läs ``~address``-bekräftelsen.

        Returnerar ALLA mottagna bytes (sync + keybytes [+ eko + ~address]). Tomt
        eller utan ledande 0x55 = ingen modul svarade på adressen. Använd
        :meth:`parse_slow_init` för att plocka ut KW1/KW2.
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
        got = bytearray(ser.read(3))  # 0x55, KW1, KW2
        if len(got) >= 3 and got[0] == 0x55:
            kw2 = got[2]
            time.sleep(w4)
            ser.reset_input_buffer()
            ser.write(bytes([(~kw2) & 0xFF]))  # ~KW2 tillbaka till ECU:n
            ser.flush()
            got += ser.read(3)  # halvduplex-eko + ~address-bekräftelse
        return bytes(got)

    def reset_input_buffer(self) -> None:
        self._require_open().reset_input_buffer()

    def _require_open(self) -> "serial.SerialBase":
        if not self._is_open or self._ser is None:
            raise RuntimeError("SerialTransport är inte öppen — anropa open() först")
        return self._ser
