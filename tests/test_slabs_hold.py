"""SLABS hold loop (test_plan T-23): one request per step, fault edges in order, death detection."""
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.slabs import Slabs
from d2diag.slabs.hold import LOG_EVERY, MISS_MAX, PATTERN, SlabsHold
from tests.fakes import FakeKLineEcu

CUR_REQ = encode(b"\x21\x47", addressed=False)
LOG_REQ = encode(b"\x21\x11", addressed=False)
WHEEL_REQ = encode(b"\x21\x43", addressed=False)
KA_REQ = encode(b"\x3e", addressed=False)          # bare 3E: 01 3e 3f
STOP_REQ = encode(b"\x82", addressed=False)

BASE_LOG = bytes.fromhex("00000010000000000000100000000000")   # 020 + 027 (the baseline)


def _block(*bits: "tuple[int, int]") -> bytes:
    b = bytearray(16)
    for byte, bit in bits:
        b[byte] |= 1 << bit
    return bytes(b)


def _resp(sid: int, lid: "int | None", data: bytes = b"") -> bytes:
    head = bytes([sid]) if lid is None else bytes([sid, lid])
    return encode(head + data, addressed=False)


def _hold(current_seq, logged=BASE_LOG, wheels=b"\x7c\x00" * 4, extra=None):
    responses = {
        CUR_REQ: [_resp(0x61, 0x47, c) for c in current_seq],
        LOG_REQ: _resp(0x61, 0x11, logged),
        WHEEL_REQ: _resp(0x61, 0x43, wheels),
        KA_REQ: _resp(0x7E, None),
    }
    responses.update(extra or {})
    ecu = FakeKLineEcu(responses)
    slabs = Slabs(KWP2000(KLine(ecu), tolerant=True))
    slabs.open()
    t = [1000.0]
    hold = SlabsHold(slabs, clock=lambda: t[0], monotonic=lambda: t[0], establish=lambda: None)
    return ecu, hold, t


def _run(hold, t, steps):
    events = []
    for _ in range(steps):
        t[0] += 1.0
        events += hold.step()
    return events


def test_one_request_per_step_in_pattern_order():
    ecu, hold, t = _hold([bytes(16)])
    hold.connect()
    ecu.sent.clear()
    _run(hold, t, len(PATTERN) * 2)
    assert len(ecu.sent) == len(PATTERN) * 2            # exactly one request per step
    assert ecu.sent[0] == CUR_REQ and ecu.sent[1] == KA_REQ
    assert ecu.sent[3] == LOG_REQ                       # first AUX slot = logged baseline early
    assert ecu.sent[7] == WHEEL_REQ


def test_onset_order_is_preserved_and_baseline_flagged():
    # current faults: none → 027 (10.4) → 027 + 020 (3.4) → only 020
    seq = [bytes(16), _block((10, 4)), _block((10, 4), (3, 4)), _block((3, 4))]
    ecu, hold, t = _hold(seq)
    hold.connect()
    edges = [e for e in _run(hold, t, 8) if e.kind == "edge"]
    cur = [(e.bit, e.state, e.seq) for e in edges if e.block == "cur"]
    assert cur == [("10.4", 1, 2), ("3.4", 1, 3), ("10.4", 0, 4)]
    assert [e.text[:3] for e in edges if e.block == "cur"] == ["027", "020", "027"]
    log = [e for e in edges if e.block == "log"]
    assert {e.bit for e in log} == {"3.4", "10.4"} and all(e.base for e in log)
    assert not any(e.base for e in edges if e.block == "cur")   # empty baseline → no base edges


def test_fault_already_present_at_connect_is_base_not_onset():
    ecu, hold, t = _hold([_block((3, 4))])
    hold.connect()
    first = [e for e in _run(hold, t, 1) if e.kind == "edge"]
    assert len(first) == 1 and first[0].base and first[0].bit == "3.4"


def test_session_death_after_miss_max_sends_82_and_reports_survival():
    # SLABS answers the first 21 47, then goes silent (as if it dropped the session on the move)
    ecu, hold, t = _hold([bytes(16)])
    hold.connect()
    _run(hold, t, 1)
    for req in (CUR_REQ, KA_REQ, WHEEL_REQ, LOG_REQ):
        ecu._responses.pop(req)
    events = _run(hold, t, MISS_MAX)
    down = [e for e in events if e.kind == "down"]
    assert len(down) == 1 and not hold.up
    assert hold.lost_after == down[0].up_s == 1.0 + MISS_MAX
    assert ecu.sent[-1] == STOP_REQ                     # link released on the shared bus


def test_single_glitch_does_not_drop_the_session():
    flaky = {KA_REQ: [b"", _resp(0x7E, None)]}            # first keepalive unanswered, then fine
    ecu, hold, t = _hold([bytes(16)], extra=flaky)
    hold.connect()
    events = _run(hold, t, len(PATTERN) * 2)
    assert hold.up and not [e for e in events if e.kind == "down"]


def test_failed_establish_reports_and_releases():
    from d2diag.kwp2000 import KWP2000Error

    def boom():
        raise KWP2000Error("no C1")

    ecu = FakeKLineEcu({})
    slabs = Slabs(KWP2000(KLine(ecu), tolerant=True))
    slabs.open()
    hold = SlabsHold(slabs, establish=boom)
    events = hold.connect()
    assert [e.kind for e in events] == ["estab_fail"] and not hold.up
    assert ecu.sent[-1] == STOP_REQ


def test_short_block_is_ignored_not_an_edge():
    ecu, hold, t = _hold([bytes(16), b"\x00\x10"])        # second current read truncated
    hold.connect()
    edges = [e for e in _run(hold, t, 3) if e.kind == "edge"]
    assert edges == [] and hold.up


def test_logged_block_reread_every_log_every_aux_slots():
    ecu, hold, t = _hold([bytes(16)])
    hold.connect()
    ecu.sent.clear()
    _run(hold, t, len(PATTERN) * (LOG_EVERY + 1))
    assert ecu.sent.count(LOG_REQ) == 2                 # baseline + one periodic re-read
