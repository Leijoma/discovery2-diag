"""Tests for the K-Line layer against a simulated half-duplex ECU (no hardware)."""
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
    # response to fast init: ECU -> tester, addressed
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
    assert ecu.breaks == [0.025]  # exactly one 25 ms low pulse
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
    # With resync, corrupt frames are skipped; with no valid frame → timeout.
    req = encode(b"\x21\x08", addressed=False)
    ecu = FakeKLineEcu({req: _session_response(b"\x61\x08\x00")}, corrupt=True)
    with KLine(ecu, timeout=0.05) as k:
        with pytest.raises(KLineTimeout):
            k.request(b"\x21\x08", retries=1)
    assert len(ecu.sent) == 2  # original attempt + 1 retry


def test_request_resyncs_past_leading_glitch():
    # The half-duplex turnaround can put a glitch byte before the ECU's frame — cf. the
    # real Td5 log: F8 before 03 7F 81 10 13. It must be skipped.
    req = encode(b"\x81", addressed=False)
    resp = encode(b"\x7f\x81\x10", addressed=False)  # = 03 7F 81 10 13
    ecu = FakeKLineEcu({req: b"\xf8" + resp})
    with KLine(ecu) as k:
        assert k.request(b"\x81") == b"\x7f\x81\x10"


def test_functional_init_does_not_mistake_its_own_echo_for_c1():
    # A FUNCTIONAL init frame itself starts with 0xC1 (c1 29 f1 81 5c). Half-duplex echoes
    # it, so a naive search for 0xC1 finds the echo and reports a connection on
    # a silent bus — exactly what happened in the car 2026-08-19 ("C1! c1 29 f1 81",
    # the 1A 8A acknowledgement dropped right afterwards).
    from d2diag.kline import KLine
    from d2diag.kline.kline import KLineTimeout
    from tests.fakes import FakeKLineEcu

    ecu = FakeKLineEcu({})               # only echoes, no ECU responds
    kl = KLine(ecu, target=0x29, timeout=0.05)
    kl.open()
    with pytest.raises(KLineTimeout):
        kl.fast_init_tolerant(functional=True, source=0xF1)


def test_functional_init_finds_a_real_c1_after_the_echo():
    from d2diag.kline import KLine, encode
    from tests.fakes import FakeKLineEcu

    req = encode(b"\x81", 0x29, 0xF1, addressed=True, functional=True)
    ecu = FakeKLineEcu({req: encode(b"\xc1\x57\x8f", addressed=False)})
    kl = KLine(ecu, target=0x29, timeout=0.05)
    kl.open()
    assert kl.fast_init_tolerant(functional=True, source=0xF1).startswith(b"\xc1\x57\x8f")


def test_write_gap_sends_one_byte_at_a_time():
    # P4 — inter-byte time in the tester's request. ISO 14230-2 specifies 5–20 ms and
    # muki01 uses 5 ms; we always sent the whole frame in one sweep. write_gap=0
    # keeps the old behaviour, >0 splits up the transmission.
    from d2diag.kline import KLine
    from tests.fakes import FakeKLineEcu

    ecu = FakeKLineEcu({})
    kl = KLine(ecu, target=0x29, timeout=0.01, write_gap=0.001)
    kl.open()
    kl.converse(b"\x81", addressed=True)
    assert [len(f) for f in ecu.sent] == [1, 1, 1, 1, 1]   # 5 bytes, one at a time

    ecu2 = FakeKLineEcu({})
    kl2 = KLine(ecu2, target=0x29, timeout=0.01)           # write_gap=0 → unchanged
    kl2.open()
    kl2.converse(b"\x81", addressed=True)
    assert [len(f) for f in ecu2.sent] == [5]


def test_init_high_compensates_for_time_already_spent_high():
    # After the low pulse the line is already high for a while before we start waiting: partly
    # the UART frame's stop bit (~2.8 ms at 360 baud), partly baudrate restore and
    # buffer flush (10–20 ms over USB). fast_init_low() returns the total
    # time and KLine subtracts it — otherwise TiniH becomes systematically too long, which
    # kept us outside the SLABS tolerance window (car 2026-08-19: 9 % → 56 % hits).
    import time as _t
    from d2diag.kline import KLine
    from tests.fakes import FakeKLineEcu

    class _Pulsing(FakeKLineEcu):
        def fast_init_low(self, low_seconds=0.025):
            return 0.010          # pretend the line has already been high for 10 ms

    ecu = _Pulsing({})
    kl = KLine(ecu, target=0x29, timeout=0.01, init_high=0.025)
    kl.open()
    t0 = _t.perf_counter()
    kl._fast_init_pulse()
    slept = _t.perf_counter() - t0
    assert slept < 0.025                       # slept ~15 ms, not 25
    assert kl.last_pulse["pre_high_ms"] == 10.0
    # Reported TiniH = stop bit + actual sleep. It should be CLOSE to 25 ms and
    # under the 35 ms it would have been without compensation. (OS sleep always overshoots a
    # little — that is exactly why the pulse must be measured and not assumed.)
    assert 25 <= kl.last_pulse["high_ms"] < 35


def test_w5_bus_idle_is_off_by_default_and_configurable():
    import time as _t
    from d2diag.kline import KLine
    from tests.fakes import FakeKLineEcu

    kl = KLine(FakeKLineEcu({}), timeout=0.01)
    assert kl.init_idle == 0.0                 # unchanged behaviour by default
    kl2 = KLine(FakeKLineEcu({}), timeout=0.01, init_idle=0.05)
    kl2.open()
    t0 = _t.perf_counter()
    kl2._fast_init_pulse()
    assert _t.perf_counter() - t0 >= 0.05      # W5 is respected
