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
    def __init__(self, kline: KLine, max_pending: int = 6) -> None:
        self._k = kline
        self._max_pending = max_pending

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
        resp = self._k.request(bytes([service]) + bytes(payload))
        resp = self._resolve_pending(resp)
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

    def _resolve_pending(self, resp: bytes) -> bytes:
        pending = 0
        while len(resp) >= 3 and resp[0] == NEGATIVE_RESPONSE and resp[2] == NRC_RESPONSE_PENDING:
            if pending >= self._max_pending:
                raise KWP2000Error("för många responsePending (0x78)")
            pending += 1
            resp = self._k.read_frame().data  # vänta in nästa svar, skicka inte om
        return resp

    # ---- tjänster ----------------------------------------------------- #
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
