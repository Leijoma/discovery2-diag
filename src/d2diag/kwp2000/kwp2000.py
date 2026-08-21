"""The KWP2000 layer (ISO 14230-3): standard services on top of K-Line.

Knows the service IDs, positive/negative responses (0x7F + NRC) and
responsePending (0x78) — but nothing about the Td5's identifiers, scaling or
seed/key algorithm (that belongs in the Td5 layer).
"""
from __future__ import annotations

from ..kline.kline import KLine

# Service IDs
START_DIAGNOSTIC_SESSION = 0x10
STOP_DIAGNOSTIC_SESSION = 0x20
STOP_COMMUNICATION = 0x82  # ISO 14230-2: ends the COMMUNICATION LINK (81 → C1)
TESTER_PRESENT = 0x3E
SECURITY_ACCESS = 0x27
READ_DATA_BY_LOCAL_ID = 0x21
INPUT_OUTPUT_CONTROL_BY_LOCAL_ID = 0x30
START_ROUTINE_BY_LOCAL_ID = 0x31
REQUEST_ROUTINE_RESULTS_BY_LOCAL_ID = 0x33

_POSITIVE = 0x40  # positive response = service ID | 0x40
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
        name = _NRC_NAMES.get(nrc, "unknown")
        super().__init__(
            f"negative response to service 0x{service:02X}: NRC 0x{nrc:02X} ({name})"
        )


class KWP2000:
    def __init__(self, kline: KLine, max_pending: int = 6, tolerant: bool = False,
                 addressed: bool = False) -> None:
        self._k = kline
        self._max_pending = max_pending
        # tolerant=True: read the whole reply burst and SEARCH for a positive/negative SID
        # instead of demanding a checksum-valid frame. For cheap, noisy
        # KKL cables where the turnaround glitch shreds individual frames.
        self._tolerant = tolerant
        # addressed=True: send ADDRESSED frames (fmt/target/source) on EVERY
        # message, not just fast init. Airbag (TRW SPS, 0x5B) runs like that — unlike
        # Td5/SLABS which switch to unaddressed session frames.
        self._addressed = addressed

    # ---- lifecycle (delegated downward) ------------------------------- #
    def open(self) -> None:
        self._k.open()

    def close(self) -> None:
        self._k.close()

    def __enter__(self) -> "KWP2000":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- generic service request -------------------------------------- #
    def request(self, service: int, payload: bytes = b"", overall: "float | None" = None,
                retries: "int | None" = None, gap: "float | None" = None) -> bytes:
        """Send a service, return the reply's data field (without the positive SID).

        Handles responsePending (0x78) by waiting for the next reply without
        retransmitting, and raises :class:`NegativeResponse` on 0x7F.
        """
        payload = bytes(payload)
        if self._tolerant:
            resp = self._request_tolerant(service, payload, overall, gap)
        else:
            kw = {} if retries is None else {"retries": retries}
            resp = self._resolve_pending(
                self._k.request(bytes([service]) + payload, addressed=self._addressed, **kw))
        if not resp:
            raise KWP2000Error(f"empty response to service 0x{service:02X}")
        if resp[0] == NEGATIVE_RESPONSE:
            nrc = resp[2] if len(resp) >= 3 else 0
            raise NegativeResponse(service, nrc)
        if resp[0] != (service | _POSITIVE):
            raise KWP2000Error(
                f"unexpected response SID 0x{resp[0]:02X} to service 0x{service:02X}"
            )
        return resp[1:]

    def _request_tolerant(self, service: int, payload: bytes,
                          overall: "float | None" = None,
                          gap: "float | None" = None) -> bytes:
        """Send via burst reading; pick the reply out of the burst without a checksum.

        Returns bytes from the found SID onward (positive or negative),
        so that the shared interpretation in :meth:`request` works unchanged.
        """
        kw = {}
        if overall is not None:
            kw["overall"] = overall
        if gap is not None:
            kw["gap"] = gap
        raw = self._k.converse(bytes([service]) + payload, addressed=self._addressed, **kw)
        return self._extract_response(raw, service, payload)

    @staticmethod
    def _extract_response(raw: bytes, service: int, payload: bytes) -> bytes:
        """Find the reply in a raw burst (echo + reply + glitch).

        Positive response: SID = service | 0x40. Prefer a 2-byte match
        [SID, echoed first payload byte] (e.g. ``61 <lid>`` / ``67 <level>``) for
        precision, otherwise the SID alone (e.g. ``50`` which has no echoed subfunction).
        The echo does not interfere: its SID is the service (0x21/0x27/…), not service|0x40.
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
                raise KWP2000Error("too many responsePending (0x78)")
            pending += 1
            resp = self._k.read_frame().data  # wait for the next reply, do not retransmit
        return resp

    # ---- services ----------------------------------------------------- #
    def start_communication(self, tolerant: "bool | None" = None,
                            functional: bool = False,
                            source: "int | None" = None) -> bytes:
        """Fast init / StartCommunication. Returns the reply's data field (C1 …).

        ``tolerant`` controls burst vs strict reading; ``None`` follows the KWP2000's
        own mode (set in the constructor)."""
        use_tolerant = self._tolerant if tolerant is None else tolerant
        if use_tolerant:
            return self._k.fast_init_tolerant(functional=functional, source=source)
        return self._k.fast_init()

    def slow_init(self, address: int) -> "tuple[int, int]":
        """5-baud slow init to a module (SLABS and others). Returns key bytes (KW1, KW2)."""
        return self._k.slow_init(address)

    def start_diagnostic_session(self, sub: int = 0xA0) -> bytes:
        return self.request(START_DIAGNOSTIC_SESSION, bytes([sub]))

    def stop_diagnostic_session(self) -> bytes:
        return self.request(STOP_DIAGNOSTIC_SESSION)

    def stop_communication(self) -> bytes:
        """StopCommunication (``82`` → ``C2``) — ends the link from StartCommunication.

        Distinct from StopDiagnosticSession: ``20`` ends a *diagnostic session*
        (Td5), ``82`` tears down the *communication link* that fast init established.
        SLABS has only the latter — it runs the services right after `81`/`C1`.
        Without `82` the ECU does not know we have left, and the next StartCommunication is met with
        ``7F 81 10`` (generalReject) until the module's own timeout expires.
        """
        # Short burst: if there is a link, C2 (or a negative response) comes within tens
        # of ms. If nothing comes within 0.5 s there was no link — don't wait out the full timeout,
        # this is on the connection path and runs before every init attempt.
        # ``retries=0``: a teardown is sent ONCE — retransmitting it against a silent
        # bus only costs a timeout, and we don't care about the reply.
        return self.request(STOP_COMMUNICATION, overall=0.5, retries=0)

    def tester_present(self, sub: "int | None" = 0x01) -> bytes:
        """TesterPresent keepalive. ``sub=None`` sends a bare ``3E`` without a sub-byte
        (SLABS wants it that way — sniffed frame ``01 3e 3f`` → ``01 7e 7f``); otherwise
        ``3E <sub>`` (standard, TD5 and others)."""
        payload = b"" if sub is None else bytes([sub])
        return self.request(TESTER_PRESENT, payload)

    def request_seed(self, level: int = 0x01) -> bytes:
        """Returns the seed bytes (without the echoed level byte)."""
        return self.request(SECURITY_ACCESS, bytes([level]))[1:]

    def send_key(self, key: bytes, level: int = 0x02) -> bytes:
        return self.request(SECURITY_ACCESS, bytes([level]) + bytes(key))

    def read_local_identifier(self, lid: int) -> bytes:
        """Returns the data field (without the echoed identifier)."""
        return self.request(READ_DATA_BY_LOCAL_ID, bytes([lid]))[1:]

    def io_control(self, lid: int, params: bytes = b"\xff") -> bytes:
        """InputOutputControlByLocalIdentifier (0x30) — output tests.

        The default param is a single ``0xFF`` (that's how the reference tool pulses TD5 outputs, e.g.
        ``30 A3 FF`` = A/C clutch). Parameterized outputs (wastegate/EGR) take
        more bytes. Returns the reply without the positive SID (starts with the echoed LID)."""
        return self.request(INPUT_OUTPUT_CONTROL_BY_LOCAL_ID, bytes([lid]) + bytes(params))

    def start_routine(self, routine: int, params: bytes = b"") -> bytes:
        """StartRoutineByLocalIdentifier (0x31). Returns the reply without the positive SID
        (i.e. starts with the echoed routine identifier)."""
        return self.request(START_ROUTINE_BY_LOCAL_ID, bytes([routine]) + bytes(params))

    def request_routine_results(self, routine: int, params: bytes = b"") -> bytes:
        """RequestRoutineResultsByLocalIdentifier (0x33). Returns the reply without the
        positive SID (starts with the echoed routine id, followed by result byte(s))."""
        return self.request(REQUEST_ROUTINE_RESULTS_BY_LOCAL_ID, bytes([routine]) + bytes(params))
