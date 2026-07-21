"""Tester för KWP2000-lagret mot en simulerad ECU (ingen hårdvara)."""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000, NegativeResponse
from tests.fakes import FakeKLineEcu


def _frame(data: bytes) -> bytes:
    return encode(data, addressed=False)


def _stack(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, KWP2000(KLine(ecu))


def test_start_diagnostic_session():
    ecu, kwp = _stack({_frame(b"\x10\xa0"): _frame(b"\x50\xa0")})
    with kwp:
        assert kwp.start_diagnostic_session(0xA0) == b"\xa0"


def test_request_seed_strips_level_returns_seed():
    ecu, kwp = _stack({_frame(b"\x27\x01"): _frame(b"\x67\x01\x34\xa5")})
    with kwp:
        assert kwp.request_seed() == b"\x34\xa5"


def test_read_local_identifier_strips_echoed_id():
    ecu, kwp = _stack({_frame(b"\x21\x08"): _frame(b"\x61\x08\x11\x22")})
    with kwp:
        assert kwp.read_local_identifier(0x08) == b"\x11\x22"


def test_negative_response_raises_with_nrc():
    ecu, kwp = _stack({_frame(b"\x10\xa0"): _frame(b"\x7f\x10\x22")})
    with kwp:
        with pytest.raises(NegativeResponse) as exc:
            kwp.start_diagnostic_session(0xA0)
    assert exc.value.service == 0x10
    assert exc.value.nrc == 0x22


def test_response_pending_then_final_without_resend():
    pending = _frame(b"\x7f\x21\x78")   # requestCorrectlyReceived-ResponsePending
    final = _frame(b"\x61\x08\x11\x22")
    ecu, kwp = _stack({_frame(b"\x21\x08"): pending + final})
    with kwp:
        assert kwp.read_local_identifier(0x08) == b"\x11\x22"
    assert len(ecu.sent) == 1  # bara EN förfrågan skickades
