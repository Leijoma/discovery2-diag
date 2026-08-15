"""Tester för den delade EcuSession-basen (livscykel, read_block, _establish).

Testar mot ``FakeKLineEcu`` genom en minimal konkret subklass, så bas-mekaniken
verifieras oberoende av Td5/Slabs. Modulernas egna establish-beteenden täcks
fortsatt av test_tolerant/test_slabs.
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
    """Modul utan efter-fas (som Slabs): fast init → klar."""

    name = "DUMMY"

    def establish(self, **kw):
        return self._establish(after=None, idle=0, attempts=2, retry_sleep=0, sleep=NOSLEEP, **kw)


def _dummy(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, _Dummy(KWP2000(KLine(ecu)))


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
    assert set(block) == {"54", "43"}                 # gemena 2-hex-nycklar (automap-format)
    assert block["54"] == bytes.fromhex("919c0f0f")
    assert block["43"] == bytes.fromhex("7c007c00")


def test_read_block_skips_failing_lid():
    # 0x54 svarar; 0x99 ger negativt svar (7F 21 12) → hoppas tyst över.
    responses = {
        _sess(b"\x21\x54"): _sess(b"\x61\x54\x91\x9c"),
        _sess(b"\x21\x99"): _sess(b"\x7f\x21\x12"),
    }
    ecu, s = _dummy(responses)
    with s:
        block = s.read_block([0x54, 0x99])
    assert set(block) == {"54"}                       # den felande LID:en finns inte med


def test_establish_after_none_returns_c1():
    ecu, s = _dummy({_init_req(): _sess(b"\xc1\x57\x8f")})
    with s:
        c1 = s.establish()
    assert c1[:3] == b"\xc1\x57\x8f"


def test_establish_raises_after_attempts_when_no_c1():
    # Ingen init-respons → tolerant fast init hittar ingen C1 → höjer efter attempts.
    ecu, s = _dummy({})
    with s:
        with pytest.raises(KWP2000Error):
            s.establish()
