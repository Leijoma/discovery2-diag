"""Tester för SLABS-skelettet: slow-init-etablering + att stubbar höjer tydligt."""
import pytest

from d2diag.kline import KLine, KLineTimeout
from d2diag.kwp2000 import KWP2000
from d2diag.slabs import KNOWN_SLABS_FAULTS, Slabs
from d2diag.transport import SerialTransport
from d2diag.transport.base import Transport


class FakeSlowTransport(Transport):
    """Minimal transport som svarar med ett fast slow-init-svar."""

    def __init__(self, response: bytes) -> None:
        self._response = response

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def send(self, data: bytes) -> int:
        return len(data)

    def receive(self, size: int = 1, timeout: "float | None" = None) -> bytes:
        return b""

    def slow_init(self, address: int) -> bytes:
        return self._response

    parse_slow_init = staticmethod(SerialTransport.parse_slow_init)


def _slabs(response: bytes) -> Slabs:
    return Slabs(KWP2000(KLine(FakeSlowTransport(response))))


def test_slabs_establish_returns_keybytes():
    with _slabs(b"\x55\x8f\xea\x70\xec") as slabs:
        assert slabs.establish(0x2C) == (0x8F, 0xEA)


def test_slabs_establish_no_response_raises():
    with _slabs(b"") as slabs:
        with pytest.raises(KLineTimeout):
            slabs.establish(0x2C)


def test_slabs_read_faults_not_implemented():
    slabs = _slabs(b"\x55\x8f\xea")
    with pytest.raises(NotImplementedError):
        slabs.read_faults()


def test_known_slabs_faults_reference():
    assert KNOWN_SLABS_FAULTS["1-1"].startswith("at start")
    assert "outlet valve" in KNOWN_SLABS_FAULTS["15-4"]
