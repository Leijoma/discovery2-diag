"""Tester för aktiv differential-mappning (tools/diffmap.py) + stödmekanik.

Täcker: skriptat FakeKLineEcu-läge (värden ändras mellan avläsningar),
``stable_diff`` (brushärdning), och diffmaps rena logik (moved/build_record/
ReadOnlyEcu-guarden). Den interaktiva CLI:n testas inte (kräver input()).
"""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.session import EcuSession
from d2diag.sniff.automap import stable_diff
from tests.fakes import FakeKLineEcu

import tools.diffmap as dm


def _f(d):
    return encode(d, addressed=False)


class _Dummy(EcuSession):
    name = "D"


# ---- skriptat FakeKLineEcu-läge ----------------------------------------- #
def test_scripted_fake_sequence_changes_between_reads():
    resp = {_f(b"\x21\x54"): [_f(b"\x61\x54\x10\x20"), _f(b"\x61\x54\x10\x99")]}
    s = _Dummy(KWP2000(KLine(FakeKLineEcu(resp))))
    with s:
        a = s.read_block([0x54])
        b = s.read_block([0x54])
    assert a["54"] == bytes.fromhex("1020")
    assert b["54"] == bytes.fromhex("1099")   # andra avläsningen skiljer


def test_scripted_fake_callable():
    resp = {_f(b"\x21\x54"): (lambda n: _f(b"\x61\x54" + bytes([n])))}
    s = _Dummy(KWP2000(KLine(FakeKLineEcu(resp))))
    with s:
        first = s.read_block([0x54])["54"]
        second = s.read_block([0x54])["54"]
    assert first == b"\x00" and second == b"\x01"


def test_static_response_still_backward_compatible():
    resp = {_f(b"\x21\x54"): _f(b"\x61\x54\xaa")}   # gammal statisk form
    s = _Dummy(KWP2000(KLine(FakeKLineEcu(resp))))
    with s:
        assert s.read_block([0x54])["54"] == b"\xaa"
        assert s.read_block([0x54])["54"] == b"\xaa"   # samma varje gång


# ---- stable_diff (brushärdning) ----------------------------------------- #
def test_stable_diff_ignores_noise_and_finds_moved_byte():
    bases = [
        {"raws": {"54": bytes.fromhex("102030")}},
        {"raws": {"54": bytes.fromhex("102530")}},   # byte1 flackar = brus
    ]
    after = {"raws": {"54": bytes.fromhex("102099")}}  # byte2 stabil 0x30 → 0x99
    mv = stable_diff(bases, after, ["54"])
    assert mv == [{"lid": "54", "byte": 2, "baseline": 0x30, "after": 0x99}]


def test_read_block_differential_over_scripted_fake():
    resp = {_f(b"\x21\x54"): [_f(b"\x61\x54\x91\x9c"), _f(b"\x61\x54\x91\xa0")]}
    s = _Dummy(KWP2000(KLine(FakeKLineEcu(resp))))
    with s:
        base = {"raws": s.read_block([0x54])}
        after = {"raws": s.read_block([0x54])}
    assert stable_diff([base], after, ["54"]) == [
        {"lid": "54", "byte": 1, "baseline": 0x9c, "after": 0xa0}
    ]


# ---- diffmap ren logik --------------------------------------------------- #
def test_build_record_numeric():
    res = {"ok": True, "mode": "numeric", "lid": "1c", "offset": 0,
           "kind": "u16", "scale": 0.0001, "bias": 0.0}
    rec = dm.build_record(res, "boost", "bar", "kandidat")
    assert rec["kind"] == "u16" and rec["lid"] == "1c"
    assert rec["scale"] == 0.0001 and rec["confidence"] == "kandidat" and rec["unit"] == "bar"


def test_build_record_state_bit_inverts_mapping():
    res = {"ok": True, "mode": "state", "lid": "56", "offset": 0, "bit": 0,
           "mapping": {"öppen": 1, "stängd": 0}}
    rec = dm.build_record(res, "any_door", "", "kandidat")
    assert rec["kind"] == "bit" and rec["bit"] == 0
    assert rec["states"] == {1: "öppen", 0: "stängd"}


def test_readonly_guard_blocks_actuators():
    class _Sess:
        def read_block(self, lids):
            return {"ok": True}

        def buzzer(self):
            raise AssertionError("ställdon ska aldrig nås via harnessen")

    ro = dm.ReadOnlyEcu(_Sess())
    assert ro.read_block([]) == {"ok": True}     # läsning tillåten
    with pytest.raises(AttributeError):
        ro.buzzer                                 # ställdon blockeras
    with pytest.raises(AttributeError):
        ro.clear_faults
