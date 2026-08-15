"""KWP2000-lagret (ISO 14230-3): standardtjänster ovanpå K-Line.

Känner till tjänste-ID:n, positiva/negativa svar (0x7F + NRC) och
responsePending (0x78) — men ingenting om Td5:ans identifiers, skalning eller
seed/key-algoritm (det hör hemma i Td5-lagret).
"""
from __future__ import annotations

from ..kline.kline import KLine

# Tjänste-ID:n
START_DIAGNOSTIC_SESSION = 0x10
STOP_DIAGNOSTIC_SESSION = 0x20
TESTER_PRESENT = 0x3E
SECURITY_ACCESS = 0x27
READ_DATA_BY_LOCAL_ID = 0x21
INPUT_OUTPUT_CONTROL_BY_LOCAL_ID = 0x30
START_ROUTINE_BY_LOCAL_ID = 0x31
REQUEST_ROUTINE_RESULTS_BY_LOCAL_ID = 0x33

_POSITIVE = 0x40  # positivt svar = tjänste-ID | 0x40
NEGATIVE_RESPONSE = 0x7F
NRC_RESPONSE_PENDING = 0x78

_NRC_NAMES = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x22: "conditionsNotCorrect",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x78: "responsePending",
}


class KWP2000Error(Exception):
    pass


class NegativeResponse(KWP2000Error):
    def __init__(self, service: int, nrc: int) -> None:
        self.service = service
        self.nrc = nrc
        name = _NRC_NAMES.get(nrc, "okänd")
        super().__init__(
            f"negativt svar på tjänst 0x{service:02X}: NRC 0x{nrc:02X} ({name})"
        )


class KWP2000:
    def __init__(self, kline: KLine, max_pending: int = 6, tolerant: bool = False,
                 addressed: bool = False) -> None:
        self._k = kline
        self._max_pending = max_pending
        # tolerant=True: läs hela svarsbursten och SÖK efter positiv/negativ SID
        # istället för att kräva en checksum-giltig ram. För billiga, brusiga
        # KKL-kablar där turnaround-glitch shreddar enstaka ramar.
        self._tolerant = tolerant
        # addressed=True: skicka ADRESSERADE ramar (fmt/target/source) på VARJE
        # meddelande, inte bara fast init. Airbag (TRW SPS, 0x5B) kör så — till
        # skillnad från Td5/SLABS som växlar till oadresserade sessionsramar.
        self._addressed = addressed

    # ---- livscykel (delegeras nedåt) ---------------------------------- #
    def open(self) -> None:
        self._k.open()

    def close(self) -> None:
        self._k.close()

    def __enter__(self) -> "KWP2000":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- generisk tjänsteförfrågan ------------------------------------ #
    def request(self, service: int, payload: bytes = b"") -> bytes:
        """Skicka en tjänst, returnera svarets datafält (utan positiv SID).

        Hanterar responsePending (0x78) genom att vänta in nästa svar utan att
        skicka om, och höjer :class:`NegativeResponse` vid 0x7F.
        """
        payload = bytes(payload)
        if self._tolerant:
            resp = self._request_tolerant(service, payload)
        else:
            resp = self._resolve_pending(
                self._k.request(bytes([service]) + payload, addressed=self._addressed))
        if not resp:
            raise KWP2000Error(f"tomt svar på tjänst 0x{service:02X}")
        if resp[0] == NEGATIVE_RESPONSE:
            nrc = resp[2] if len(resp) >= 3 else 0
            raise NegativeResponse(service, nrc)
        if resp[0] != (service | _POSITIVE):
            raise KWP2000Error(
                f"oväntad svars-SID 0x{resp[0]:02X} på tjänst 0x{service:02X}"
            )
        return resp[1:]

    def _request_tolerant(self, service: int, payload: bytes) -> bytes:
        """Skicka via burst-läsning; plocka svaret ur bursten utan checksum.

        Returnerar bytes från och med den funna SID:en (positiv eller negativ),
        så att den gemensamma tolkningen i :meth:`request` fungerar oförändrad.
        """
        raw = self._k.converse(bytes([service]) + payload, addressed=self._addressed)
        return self._extract_response(raw, service, payload)

    @staticmethod
    def _extract_response(raw: bytes, service: int, payload: bytes) -> bytes:
        """Hitta svaret i en rå burst (eko + svar + glitch).

        Positivt svar: SID = service | 0x40. Föredra en 2-byte-träff
        [SID, ekad första payloadbyte] (t.ex. ``61 <lid>`` / ``67 <nivå>``) för
        precision, annars enbart SID (t.ex. ``50`` som saknar ekad subfunktion).
        Ekot stör inte: dess SID är service (0x21/0x27/…), inte service|0x40.
        """
        sid = service | _POSITIVE
        pos = -1
        if payload:
            pos = raw.find(bytes([sid, payload[0]]))
        if pos < 0:
            pos = raw.find(bytes([sid]))
        neg = raw.find(bytes([NEGATIVE_RESPONSE, service]))
        if pos >= 0 and (neg < 0 or pos <= neg):
            return raw[pos:]
        if neg >= 0:
            return raw[neg:]
        return b""

    def _resolve_pending(self, resp: bytes) -> bytes:
        pending = 0
        while len(resp) >= 3 and resp[0] == NEGATIVE_RESPONSE and resp[2] == NRC_RESPONSE_PENDING:
            if pending >= self._max_pending:
                raise KWP2000Error("för många responsePending (0x78)")
            pending += 1
            resp = self._k.read_frame().data  # vänta in nästa svar, skicka inte om
        return resp

    # ---- tjänster ----------------------------------------------------- #
    def start_communication(self, tolerant: "bool | None" = None) -> bytes:
        """Fast init / StartCommunication. Returnerar svarets datafält (C1 …).

        ``tolerant`` styr burst- vs strikt läsning; ``None`` följer KWP2000:ans
        eget läge (satt i konstruktorn)."""
        use_tolerant = self._tolerant if tolerant is None else tolerant
        return self._k.fast_init_tolerant() if use_tolerant else self._k.fast_init()

    def slow_init(self, address: int) -> "tuple[int, int]":
        """5-baud slow init mot en modul (SLABS m.fl.). Returnerar keybytes (KW1, KW2)."""
        return self._k.slow_init(address)

    def start_diagnostic_session(self, sub: int = 0xA0) -> bytes:
        return self.request(START_DIAGNOSTIC_SESSION, bytes([sub]))

    def stop_diagnostic_session(self) -> bytes:
        return self.request(STOP_DIAGNOSTIC_SESSION)

    def tester_present(self, sub: int = 0x01) -> bytes:
        return self.request(TESTER_PRESENT, bytes([sub]))

    def request_seed(self, level: int = 0x01) -> bytes:
        """Returnerar seed-bytes (utan den ekade nivåbyten)."""
        return self.request(SECURITY_ACCESS, bytes([level]))[1:]

    def send_key(self, key: bytes, level: int = 0x02) -> bytes:
        return self.request(SECURITY_ACCESS, bytes([level]) + bytes(key))

    def read_local_identifier(self, lid: int) -> bytes:
        """Returnerar datafältet (utan den ekade identifieraren)."""
        return self.request(READ_DATA_BY_LOCAL_ID, bytes([lid]))[1:]

    def io_control(self, lid: int, params: bytes = b"\xff") -> bytes:
        """InputOutputControlByLocalIdentifier (0x30) — output-tester.

        Standard-param är en enda ``0xFF`` (så Nanacom pulsar TD5-utgångar, t.ex.
        ``30 A3 FF`` = A/C-koppling). Parametriserade utgångar (wastegate/EGR) tar
        fler bytes. Returnerar svaret utan positiv SID (börjar med ekad LID)."""
        return self.request(INPUT_OUTPUT_CONTROL_BY_LOCAL_ID, bytes([lid]) + bytes(params))

    def start_routine(self, routine: int, params: bytes = b"") -> bytes:
        """StartRoutineByLocalIdentifier (0x31). Returnerar svaret utan positiv SID
        (dvs börjar med den ekade rutin-identifieraren)."""
        return self.request(START_ROUTINE_BY_LOCAL_ID, bytes([routine]) + bytes(params))

    def request_routine_results(self, routine: int, params: bytes = b"") -> bytes:
        """RequestRoutineResultsByLocalIdentifier (0x33). Returnerar svaret utan
        positiv SID (börjar med ekad rutin-id, följt av resultatbyte/-bytes)."""
        return self.request(REQUEST_ROUTINE_RESULTS_BY_LOCAL_ID, bytes([routine]) + bytes(params))
