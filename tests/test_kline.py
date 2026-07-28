"""Tester för K-Line-lagret mot en simulerad halv-duplex-ECU (ingen hårdvara)."""
import pytest

from d2diag.kline import (
    TD5_ECU_ADDRESS,
    TESTER_ADDRESS,
    KLine,
    KLineTimeout,
    encode,
)
from tests.fakes import FakeKLineEcu


def _session_response(data: bytes) -> bytes:
    return encode(data, addressed=False)


def _init_response(data: bytes) -> bytes:
    # svar på fast init: ECU -> tester, adresserat
    return encode(data, target=TESTER_ADDRESS, source=TD5_ECU_ADDRESS, addressed=True)


def test_request_nonaddressed_roundtrip():
    req = encode(b"\x3e\x01", addressed=False)
    ecu = FakeKLineEcu({req: _session_response(b"\x7e\x01")})
    with KLine(ecu) as k:
        assert k.request(b"\x3e\x01") == b"\x7e\x01"
    assert ecu.sent[0] == req


def test_fast_init_pulses_low_and_returns_data():
    req = encode(b"\x81", addressed=True)  # 81 13 F7 81 0C
    ecu = FakeKLineEcu({req: _init_response(b"\xc1\xea\x8f")})
    with KLine(ecu) as k:
        assert k.fast_init() == b"\xc1\xea\x8f"
    assert ecu.breaks == [0.025]  # exakt en 25 ms låg-puls
    assert ecu.sent[0] == bytes.fromhex("8113F7810C")


def test_echo_is_swallowed_not_returned():
    req = encode(b"\x3e", addressed=False)
    ecu = FakeKLineEcu({req: _session_response(b"\x7e")})
    with KLine(ecu) as k:
        assert k.request(b"\x3e") == b"\x7e"


def test_timeout_when_no_response():
    ecu = FakeKLineEcu({})
    with KLine(ecu, timeout=0.05) as k:
        with pytest.raises(KLineTimeout):
            k.request(b"\x81", retries=0)


def test_corrupt_frame_is_skipped_and_times_out():
    # Med resync hoppas trasiga ramar över; finns ingen giltig ram → timeout.
    req = encode(b"\x21\x08", addressed=False)
    ecu = FakeKLineEcu({req: _session_response(b"\x61\x08\x00")}, corrupt=True)
    with KLine(ecu, timeout=0.05) as k:
        with pytest.raises(KLineTimeout):
            k.request(b"\x21\x08", retries=1)
    assert len(ecu.sent) == 2  # ursprungsförsök + 1 retry


def test_request_resyncs_past_leading_glitch():
    # Halvduplex-vändningen kan lägga en glitch-byte före ECU:ns ram — jfr den
    # riktiga Td5-loggen: F8 före 03 7F 81 10 13. Den ska hoppas över.
    req = encode(b"\x81", addressed=False)
    resp = encode(b"\x7f\x81\x10", addressed=False)  # = 03 7F 81 10 13
    ecu = FakeKLineEcu({req: b"\xf8" + resp})
    with KLine(ecu) as k:
        assert k.request(b"\x81") == b"\x7f\x81\x10"
