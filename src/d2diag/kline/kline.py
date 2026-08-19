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


def _precise_wait(seconds: float) -> None:
    """Vänta ``seconds`` med sub-millisekundsprecision.

    ``time.sleep`` överskjuter: uppmätt på macOS ger ``sleep(25 ms)`` i själva
    verket 25,3–32,0 ms (median 29,1). För TiniH, som ISO 14230-2 sätter till
    25 ms ± 1, är det för trubbigt. Vi sover därför bara fram till 2 ms före målet
    och snurrar sista biten — 25 ms brända CPU-cykler en gång per anslutningsförsök
    är ett billigt pris för en puls inom toleransen.
    """
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    # Grovsömn bara för långa väntor: en sleep() kan överskjuta 5–7 ms, så för
    # init-pulsens 25 ms skulle den ensam missa målet. Snurra hela vägen i stället.
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
        # P4 — inter-byte-tid i testarens förfrågan. ISO 14230-2 anger 5–20 ms, och
        # muki01-referensen (bekräftad korrekt) skickar en byte i taget med 5 ms
        # emellan. Vi har alltid skickat hela ramen i ett svep (~1 ms/byte vid
        # 10400 baud), vilket en strikt ECU kan vägra parsa. 0.0 = gammalt beteende.
        self.write_gap = write_gap
        # ISO 14230-2 fast init: TiniL = 25 ms ± 1 låg, sedan 25 ms ± 1 hög, sedan
        # StartCommunication. Låg-pulsen är hårdvarutimad (baud-drop), men den HÖGA
        # perioden är time.sleep() och det som händer efteråt — flush + USB-write —
        # ligger utanför vår kontroll. En FTDI/CH340 buffrar dessutom med sin
        # latency timer (default 16 ms), så den faktiska tiden till första byten kan
        # bli 25–45 ms i stället för 25. Därav justerbart, och mätt: se last_pulse.
        self.init_low = init_low
        self.init_high = init_high
        # W5 — buss-idle före fast init. ISO 14230-2 anger 300 ms; vi hade inget alls.
        # 0.0 = av (gammalt beteende); sätt 0.3–1.0 för att eliminera W5 som variabel.
        self.init_idle = init_idle
        self.last_pulse: "dict" = {}
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
    def _fast_init_pulse(self) -> None:
        """Den fysiska init-pulsen: linjen låg ``init_low``, sedan hög ``init_high``.

        Mäter vad som FAKTISKT hände (``last_pulse``) — nominella värden säger inget
        om en USB-serieport där drivrutin och OS lägger på egen fördröjning.
        """
        if self.init_idle:
            time.sleep(self.init_idle)   # W5: låt bussen vara tyst före pulsen
        t0 = time.perf_counter()
        self._flush_input()
        # Deterministisk låg-puls: föredra baud-drop (0x00 @ ~360 baud) framför
        # OS-timad break, vars längd jittrar på icke-realtids-OS och gör att Td5:an
        # aldrig går in i diag-läge (03 7F 81 10 = generalReject).
        already_high = 0.0
        pulse = getattr(self._t, "fast_init_low", None)
        if pulse is not None:
            already_high = pulse(self.init_low) or 0.0
        else:
            send_break = getattr(self._t, "send_break", None)
            if send_break is None:
                raise KLineError(
                    "transporten saknar fast_init_low()/send_break() — krävs för fast init"
                )
            send_break(self.init_low)
        t1 = time.perf_counter()
        # Dra av den tid linjen REDAN varit hög (UART-stoppbiten efter puls-byten),
        # annars blir TiniH systematiskt för lång.
        _precise_wait(max(0.0, self.init_high - already_high))
        t2 = time.perf_counter()
        self.last_pulse = {"low_ms": round((t1 - t0) * 1000, 1),
                           "high_ms": round((t2 - t1) * 1000 + already_high * 1000, 1),
                           "pre_high_ms": round(already_high * 1000, 1)}

    def fast_init(self, start_communication: bytes = DEFAULT_START_COMMUNICATION) -> bytes:
        """Kör fast init (adresserad StartCommunication) och returnerar svarets
        datafält (t.ex. nyckelbytes). Strikt ram-läsning."""
        self._fast_init_pulse()
        # Ingen retry: StartCommunication ska skickas EN gång. Lyckas den öppnas
        # sessionen; en omsändning avvisas då (generalReject "redan i session").
        return self.request(start_communication, addressed=True, retries=0)

    def fast_init_tolerant(
        self,
        start_communication: bytes = DEFAULT_START_COMMUNICATION,
        functional: bool = False,
        source: "int | None" = None,
    ) -> bytes:
        """Fast init med tolerant burst-läsning: sök 0xC1 i hela svarsbursten.

        Returnerar bursten från och med 0xC1 (C1 + nyckelbytes, ev. följt av
        glitch). Höjer :class:`KLineTimeout` om inget C1 syns. Poängen: en
        brusskadad C1-ram (t.ex. ``03 c1 38 0e f8 00``) INNEHÅLLER ändå 0xC1, så
        vi ser "session öppen" på första försöket och slipper init-om-loopen som
        annars öppnar sessionen upprepat och låser ECU:n (``7F`` generalReject).
        """
        self._fast_init_pulse()
        t_send = time.perf_counter()
        frame = encode(start_communication, self._target,
                       self._source if source is None else source,
                       addressed=True, functional=functional)
        raw = self.converse(start_communication, addressed=True,
                            functional=functional, source=source)
        # to_frame_ms = tiden från pulsens slut tills SÄNDNINGEN startade (inte hela
        # konversationen — burst-läsningen ingår inte). send_ms = själva utskrivningen.
        self.last_pulse["to_frame_ms"] = round(
            (time.perf_counter() - t_send) * 1000 - getattr(self, "_last_send_ms", 0.0), 1)
        self.last_pulse["send_ms"] = getattr(self, "_last_send_ms", 0.0)
        # HOPPA ÖVER EKOT innan vi söker C1. Halv-duplex ekar allt vi sänder, och
        # en FUNKTIONELL ram börjar själv på 0xC1 — utan detta hittar sökningen
        # vårt eget eko och rapporterar "session established" på tomma bussen
        # (bilen 2026-08-19: `C1! c1 29 f1 81` = ekot, kvittensen 1A 8A föll).
        i = raw.find(frame)
        if i >= 0:
            search, offset = raw[i + len(frame):], i + len(frame)
        elif functional:
            # Ekot glitchade. Sök ändå inte i de första bytes där det låg — ett
            # 0xC1 där är med största sannolikhet vårt eget.
            search, offset = raw[len(frame):], len(frame)
        else:
            search, offset = raw, 0   # fysiskt eko (0x8n) innehåller inget 0xC1
        j = search.find(0xC1)
        if j < 0:
            # Var tydlig med att ekot är bortsett: en funktionell ram BÖRJAR på 0xC1,
            # så "ingen C1 i bursten" läste fel mot en burst som syns börja med c1.
            raise KLineTimeout(
                f"inget svar efter ekot (eko {frame.hex(' ')}, "
                f"burst {raw.hex(' ') or 'tom'})")
        return raw[offset + j:]

    def slow_init(self, address: int) -> "tuple[int, int]":
        """5-baud slow init mot en modul (t.ex. SLABS — motorn använder fast init).

        Returnerar keybytes (KW1, KW2). Höjer :class:`KLineTimeout` om ingen modul
        svarar (inget 0x55 i svaret). Kräver att transporten stöder ``slow_init``.
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
                f"ingen slow-init-respons på 0x{address:02X}: {raw.hex(' ') or 'tomt'}"
            )
        return kw

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
                if self._echo:
                    self.read_frame()  # konsumera vårt eget eko (första giltiga ram)
                return self.read_frame().data  # svaret = nästa giltiga ram
            except (KLineTimeout, ChecksumError, FrameError) as exc:
                last = exc
        assert last is not None
        raise last

    # ---- tolerant burst-I/O (brusiga billiga KKL-kablar) -------------- #
    def converse(
        self,
        data: bytes,
        addressed: bool = False,
        gap: float = 0.06,
        overall: float = 1.0,
        functional: bool = False,
        source: "int | None" = None,
    ) -> bytes:
        """Skicka ett datafält och läs HELA svarsbursten rått (eko + svar +
        ev. glitchbytes) — utan checksum-avvisning.

        Motsatsen till :meth:`request`: här valideras ingen ram. Callern söker
        själv efter förväntad svarsbyte i bursten. Avsett för billiga KKL-kablar
        där turnaround-glitch shreddar enstaka ramar men rätt byte ändå finns med.
        """
        frame = encode(data, self._target, self._source if source is None else source,
                       addressed=addressed, functional=functional)
        self._flush_input()
        self._send(frame)
        return self._burst_read(gap, overall)

    def _burst_read(self, gap: float, overall: float) -> bytes:
        """Samla bytes tills det blir tyst i ``gap`` s (inter-byte-gap), dock högst
        ``overall`` s totalt. muki01-stil: läs hela bursten, tolka den sedan."""
        buf = bytearray()
        start = time.monotonic()
        got = False
        while time.monotonic() - start < overall:
            chunk = self._t.receive(64, timeout=gap)
            if chunk:
                buf += chunk
                got = True
            elif got:
                break  # tystnad efter data → bursten är klar
            else:
                time.sleep(0.002)  # väntar fortfarande på första byten
        return bytes(buf)

    def _send(self, frame: bytes) -> None:
        """Sänd en ram, med P4-mellanrum mellan byten om ``write_gap`` är satt."""
        t0 = time.perf_counter()
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
                time.sleep(self.write_gap)

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
            if length < 1:
                continue  # tom ram = falskt positivt i brus, hoppa
            end = idx + length
            if end + 1 > n:
                continue  # ofullständig för den här startpunkten
            try:
                return decode(bytes(buf[start : end + 1])), end + 1
            except (FrameError, ChecksumError):
                continue
        return None, 0

    # ---- lågnivå ------------------------------------------------------ #
    def _flush_input(self) -> None:
        self._rxbuf.clear()
        flush = getattr(self._t, "reset_input_buffer", None)
        if flush is not None:
            flush()
