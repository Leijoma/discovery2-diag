"""Tester för K-Line-lagret mot en simulerad ECU (ingen hårdvara)."""
import pytest

from d2diag.kline import (
    TD5_ECU_ADDRESS,
    TESTER_ADDRESS,
    ChecksumError,
    KLine,
    KLineTimeout,
    encode,
)
from tests.fakes import FakeKLineEcu


def _response(data: bytes) -> bytes:
    """Svarsram: ECU -> tester."""
    return encode(data, target=TESTER_ADDRESS, source=TD5_ECU_ADDRESS)


def test_request_returns_response_data():
    req = encode(b"\x81")
    ecu = FakeKLineEcu({req: _response(b"\xc1\xea\x8f")})
    with KLine(ecu) as k:
        assert k.request(b"\x81") == b"\xc1\xea\x8f"
    assert ecu.sent[0] == req  # rätt ram skickades


def test_echo_is_swallowed_not_returned():
    req = encode(b"\x3e")  # TesterPresent
    ecu = FakeKLineEcu({req: _response(b"\x7e")})
    with KLine(ecu) as k:
        # ekot (req) får inte läcka in i svaret
        assert k.request(b"\x3e") == b"\x7e"


def test_fast_init_pulses_low_and_returns_keybytes():
    req = encode(b"\x81")
    ecu = FakeKLineEcu({req: _response(b"\xc1\xea\x8f")})
    with KLine(ecu) as k:
        key = k.fast_init()
    assert key == b"\xc1\xea\x8f"
    assert ecu.breaks == [0.025]  # exakt en 25 ms låg-puls


def test_timeout_when_no_response():
    ecu = FakeKLineEcu({})  # ingen svarsmappning
    with KLine(ecu, timeout=0.05) as k:
        with pytest.raises(KLineTimeout):
            k.request(b"\x81", retries=0)


def test_checksum_error_retries_then_raises():
    req = encode(b"\x81")
    ecu = FakeKLineEcu({req: _response(b"\xc1\xea\x8f")}, corrupt=True)
    with KLine(ecu) as k:
        with pytest.raises(ChecksumError):
            k.request(b"\x81", retries=1)
    assert len(ecu.sent) == 2  # ursprungsförsök + 1 retry
