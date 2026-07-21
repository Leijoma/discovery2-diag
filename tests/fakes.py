"""Testhjälpmedel: en halv-duplex-ECU-simulator på Transport-nivå.

Ekar varje sänd ram (som en riktig K-line) och köar ett förprogrammerat svar när
en känd förfrågan skickas. Låter hela K-Line-lagret testas utan hårdvara.
"""
from __future__ import annotations

from d2diag.transport.base import Transport


class FakeKLineEcu(Transport):
    def __init__(self, responses: "dict[bytes, bytes] | None" = None, corrupt: bool = False) -> None:
        self._rx = bytearray()
        self._responses = {bytes(k): bytes(v) for k, v in (responses or {}).items()}
        self._corrupt = corrupt
        self.breaks: "list[float]" = []
        self.sent: "list[bytes]" = []

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def send(self, data: bytes) -> int:
        data = bytes(data)
        self.sent.append(data)
        self._rx.extend(data)  # eko (halv-duplex)
        resp = self._responses.get(data)
        if resp is not None:
            if self._corrupt:
                resp = resp[:-1] + bytes([resp[-1] ^ 0xFF])  # trasig checksumma
            self._rx.extend(resp)
        return len(data)

    def receive(self, size: int = 1, timeout: "float | None" = None) -> bytes:
        out = bytes(self._rx[:size])
        del self._rx[: len(out)]
        return out

    # seriella lågnivåhooks som K-Line-lagret använder
    def send_break(self, duration: float = 0.025) -> None:
        self.breaks.append(duration)

    def reset_input_buffer(self) -> None:
        self._rx.clear()
