"""Test för Td5-lagret: hela stacken Td5 → KWP2000 → K-Line → simulerad ECU."""
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Td5
from d2diag.td5.keygen import key_bytes_from_seed
from tests.fakes import FakeKLineEcu


def _frame(data: bytes) -> bytes:
    return encode(data, addressed=False)


def test_unlock_computes_and_sends_correct_key():
    seed = b"\x34\xa5"
    key = key_bytes_from_seed(seed[0], seed[1])
    responses = {
        _frame(b"\x27\x01"): _frame(b"\x67\x01" + seed),            # seed
        _frame(b"\x27\x02" + key): _frame(b"\x67\x02"),            # nyckel accepteras
    }
    ecu = FakeKLineEcu(responses)
    with Td5(KWP2000(KLine(ecu))) as td5:
        td5.unlock()
    assert _frame(b"\x27\x02" + key) in ecu.sent  # rätt nyckel skickades


def test_start_session():
    ecu = FakeKLineEcu({_frame(b"\x10\xa0"): _frame(b"\x50\xa0")})
    with Td5(KWP2000(KLine(ecu))) as td5:
        assert td5.start_session() == b"\xa0"
