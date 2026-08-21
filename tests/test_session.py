"""Tests for the shared EcuSession base (lifecycle, read_block, _establish).

Tests against ``FakeKLineEcu`` through a minimal concrete subclass, so the base
mechanics are verified independently of Td5/Slabs. The modules' own establish
behaviours are still covered by test_tolerant/test_slabs.
"""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000, KWP2000Error
from d2diag.session import EcuSession
from tests.fakes import FakeKLineEcu

NOSLEEP = lambda *_: None  # noqa: E731


def _sess(data: bytes) -> bytes:
    return encode(data, addressed=False)


def _init_req() -> bytes:
    return encode(b"\x81", addressed=True)


class _Dummy(EcuSession):
    """Module without an after phase (like Slabs): fast init → done."""

    name = "DUMMY"

    def establish(self, **kw):
        return self._establish(after=None, idle=0, attempts=2, retry_sleep=0, sleep=NOSLEEP, **kw)


def _dummy(responses):
    # short frame timeout: the tests should not pay 1 s per missing response
    ecu = FakeKLineEcu(responses)
    return ecu, _Dummy(KWP2000(KLine(ecu, timeout=0.05)))


def test_context_manager_opens_and_closes():
    ecu, s = _dummy({})
    assert not getattr(ecu, "_is_open", False)
    with s:
        assert ecu._is_open is True
    assert ecu._is_open is False


def test_read_local_strips_echoed_lid():
    responses = {_sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c\x0f\x0f")}
    ecu, s = _dummy(responses)
    with s:
        assert s.read_local(0x54) == bytes.fromhex("919c0f0f")


def test_read_block_returns_lid_hex_keyed_bytes():
    responses = {
        _sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c\x0f\x0f"),
        _sess(b"\x21\x43"): _sess(b"\x61\x43\x7c\x00\x7c\x00"),
    }
    ecu, s = _dummy(responses)
    with s:
        block = s.read_block([0x54, 0x43])
    assert set(block) == {"54", "43"}                 # lowercase 2-hex keys (automap format)
    assert block["54"] == bytes.fromhex("919c0f0f")
    assert block["43"] == bytes.fromhex("7c007c00")


def test_read_block_skips_failing_lid():
    # 0x54 responds; 0x99 gives a negative response (7F 21 12) → silently skipped.
    responses = {
        _sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c"),
        _sess(b"\x21\x99"): _sess(b"\x7f\x21\x12"),
    }
    ecu, s = _dummy(responses)
    with s:
        block = s.read_block([0x54, 0x99])
    assert set(block) == {"54"}                       # the failing LID is not included


def test_establish_after_none_returns_c1():
    ecu, s = _dummy({_init_req(): _sess(b"\xc1\x57\x8f")})
    with s:
        c1 = s.establish()
    assert c1[:3] == b"\xc1\x57\x8f"


def test_establish_raises_after_attempts_when_no_c1():
    # No init response → tolerant fast init finds no C1 → raises after attempts.
    ecu, s = _dummy({})
    with s:
        with pytest.raises(KWP2000Error):
            s.establish()


# ---- clean teardown on a shared bus (release/end_session) ---------------- #

class _WithSession(_Dummy):
    """Module WITH a diagnostic session (like Td5) — should close cleanly."""

    name = "WITHSESSION"
    _has_session = True


def test_release_sends_stop_diagnostic_session_then_closes():
    # Td5 case: release() should send StopDiagnosticSession (20 → 60) BEFORE the port
    # is closed, otherwise the session lingers and the next module's init gets 7F 81 10.
    ecu = FakeKLineEcu({_sess(b"\x20"): _sess(b"\x60"), _sess(b"\x82"): _sess(b"\xc2")})
    s = _WithSession(KWP2000(KLine(ecu)))
    with s:
        s.release()
    # Td5 has BOTH: a diagnostic session (20) on top of the communication link (82).
    assert ecu.sent == [_sess(b"\x20"), _sess(b"\x82")]
    assert ecu._is_open is False


def test_release_without_session_still_stops_communication():
    # SLABS case: no diagnostic session to end — but fast init established
    # a LINK, and it must be torn down with 82. Otherwise the module answers 7F 81 10 on the next
    # StartCommunication until its own timeout expires (confirmed in the car 2026-08-18).
    ecu, s = _dummy({_sess(b"\x82"): _sess(b"\xc2")})
    with s:
        s.release()
    assert ecu.sent == [_sess(b"\x82")]     # 82, but no 20 (no session)
    assert ecu._is_open is False


def test_release_closes_even_when_stop_fails():
    # Silent/dead bus: 20 gets no response. The close must not hang on it.
    ecu = FakeKLineEcu({})  # no response to 20
    s = _WithSession(KWP2000(KLine(ecu, timeout=0.01)))
    with s:
        s.release()
    assert ecu._is_open is False


def test_establish_clears_stale_link_before_init():
    # A link left open (crashed process, previous run) makes the module
    # answer 7F 81 10 on StartCommunication. We tear it down with 82 BEFORE every attempt.
    ecu, s = _dummy({_init_req(): _sess(b"\xc1\x57\x8f"), _sess(b"\x82"): _sess(b"\xc2")})
    with s:
        assert s.establish().startswith(b"\xc1\x57\x8f")  # burst from C1 (+ checksum)
    assert ecu.sent[0] == _sess(b"\x82")    # cleanup first …
    assert ecu.sent[1] == _init_req()       # … then init


def test_establish_progress_reports_the_burst_on_each_failed_try():
    # The burst (e.g. "03 7f 81 10 13") should appear in the connection log for EVERY
    # failed attempt — otherwise you can't tell whether the reject was there from the start.
    ecu, s = _dummy({})                     # no response to either 82 or init
    msgs: "list[str]" = []
    with s:
        with pytest.raises(KWP2000Error):
            s.establish(progress=msgs.append)
    tries = [m for m in msgs if m.startswith("no response yet")]
    assert len(tries) == 2                  # attempts=2 in _Dummy
    assert all("burst" in m for m in tries)


def test_stale_link_is_cleared_once_not_between_tries():
    # The pause between attempts must be SILENT. If we send 82 before every attempt
    # the module's wait is reset and it never releases its link (measured in the sniff:
    # every successful SLABS init came after 25–28 s of no traffic to the module).
    ecu, s = _dummy({})                      # no response → all attempts fail
    with pytest.raises(KWP2000Error):
        with s:
            s.establish()
    stops = [f for f in ecu.sent if f == _sess(b"\x82")]
    assert len(stops) == 1                   # exactly one cleanup, before the silence
    assert ecu.sent[0] == _sess(b"\x82")     # and it came first of all


def test_end_session_leaves_the_port_open_but_release_closes_it():
    # Shared port: tools/slabs_probe.py reads TD5 first and THEN tests SLABS on
    # the same transport. If TD5 is ended with release() the port closes, and every following
    # init attempt "fails" without a byte going out — a test error that looks like
    # a silent module (car 2026-08-19, 6.5 min wasted). end_session() may
    # therefore end the session WITHOUT closing.
    ecu = FakeKLineEcu({_sess(b"\x20"): _sess(b"\x60"), _sess(b"\x82"): _sess(b"\xc2")})
    s = _WithSession(KWP2000(KLine(ecu)))
    s.open()
    s.end_session()
    assert ecu.sent == [_sess(b"\x20"), _sess(b"\x82")]
    assert ecu.is_open is True          # the port lives on for the next module
    s.release()
    assert ecu.is_open is False
