"""Tester för det toleranta läget: burst-läsning som klarar brus där strikt fallerar.

Bevisar mot INSPELADE bytes (verklig bil 2026-08-03) och simulerad turnaround-
glitch att biblioteket tar sig hela vägen till upplåst livedata.
"""
import pytest

from d2diag.kline import (
    TD5_ECU_ADDRESS,
    TESTER_ADDRESS,
    KLine,
    KLineTimeout,
    encode,
)
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Td5
from d2diag.td5.keygen import key_bytes_from_seed
from tests.fakes import FakeKLineEcu

NOSLEEP = lambda *_: None  # noqa: E731 — injiceras i establish() så testerna är snabba


def _sess(data: bytes) -> bytes:
    """Oadresserad sessionsram (så ECU-svaren ser ut som på bilen)."""
    return encode(data, addressed=False)


def _init_req() -> bytes:
    return encode(b"\x81", addressed=True)  # 81 13 F7 81 0C


# --------------------------------------------------------------------------- #
# KLine: converse + tolerant fast init
# --------------------------------------------------------------------------- #
def test_converse_returns_echo_plus_response():
    req = _sess(b"\x3e\x01")
    resp = _sess(b"\x7e\x01")
    ecu = FakeKLineEcu({req: resp})
    with KLine(ecu) as k:
        burst = k.converse(b"\x3e\x01")
    assert burst == req + resp  # hela bursten rå: eko följt av svar


def test_fast_init_tolerant_finds_c1_in_shredded_frame():
    # C1 finns men ramen är sönderskjuten av turnaround-glitch (som på bilen).
    ecu = FakeKLineEcu({_init_req(): b"\x03\xc1\x38\x0e\xf8\x00"})
    with KLine(ecu) as k:
        out = k.fast_init_tolerant()
    assert out[0] == 0xC1


def test_strict_fast_init_fails_where_tolerant_succeeds():
    ecu = FakeKLineEcu({_init_req(): b"\x03\xc1\x38\x0e\xf8\x00"})
    with KLine(ecu) as k:
        with pytest.raises(KLineTimeout):
            k.fast_init()  # strikt kräver giltig ram → faller


# --------------------------------------------------------------------------- #
# KWP2000: tolerant request plockar svaret trots trasig checksumma
# --------------------------------------------------------------------------- #
def test_tolerant_request_survives_bad_checksum():
    req = _sess(b"\x21\x09")
    good = _sess(b"\x61\x09\x00\x00")
    ecu = FakeKLineEcu({req: good}, corrupt=True)  # checksumman flippas
    with KWP2000(KLine(ecu), tolerant=True) as kwp:
        data = kwp.read_local_identifier(0x09)
    assert data.startswith(b"\x00\x00")  # 61 09 hittades trots trasig cs


def test_strict_request_fails_on_bad_checksum():
    req = _sess(b"\x21\x09")
    good = _sess(b"\x61\x09\x00\x00")
    ecu = FakeKLineEcu({req: good}, corrupt=True)
    with KWP2000(KLine(ecu)) as kwp:  # strikt
        with pytest.raises(Exception):
            kwp.read_local_identifier(0x09)


def test_tolerant_negative_response_still_raises():
    from d2diag.kwp2000 import NegativeResponse

    req = _sess(b"\x10\xa0")
    neg = _sess(b"\x7f\x10\x10")  # generalReject
    ecu = FakeKLineEcu({req: neg})
    with KWP2000(KLine(ecu), tolerant=True) as kwp:
        with pytest.raises(NegativeResponse):
            kwp.start_diagnostic_session(0xA0)


# --------------------------------------------------------------------------- #
# Td5: full establish() inkl. keygen, mot sniffens exakta bytes
# --------------------------------------------------------------------------- #
def _sniff_ecu(corrupt: bool = False) -> FakeKLineEcu:
    seed_hi, seed_lo = 0x10, 0xE6                 # seed ur Ekaitza-sniffen
    key = key_bytes_from_seed(seed_hi, seed_lo)   # vår keygen → 90 86
    responses = {
        _init_req(): _sess(b"\xc1\x57\x8f"),                              # 03 c1 57 8f aa
        _sess(b"\x10\xa0"): _sess(b"\x50"),                              # 01 50 51
        _sess(b"\x27\x01"): _sess(b"\x67\x01" + bytes([seed_hi, seed_lo])),  # 04 67 01 10 e6 62
        _sess(b"\x27\x02" + key): _sess(b"\x67\x02"),                    # 02 67 02 6b
    }
    return FakeKLineEcu(responses, corrupt=corrupt)


def test_establish_full_flow_including_keygen():
    td5 = Td5(KWP2000(KLine(_sniff_ecu()), tolerant=True))
    with td5:
        c1 = td5.establish(idle=0, attempts=2, sleep=NOSLEEP)
    # Nyckeln accepterades bara om vår keygen matchade sniffens seed→key.
    assert c1[:3] == b"\xc1\x57\x8f"


def test_read_real_recorded_lid_1a_decodes_temps():
    # Verklig 21 1A-svarsram från bilen (RDL 016, 2026-08-03, motor av):
    #   12 61 1a | 0c fc 04 f1 0c b1 05 eb 10 88 00 04 0c 95 06 51 | cb
    # kylvätska = offset 0 u16 = 0x0cfc = 3324 → 332.4 − 273.2 = 59.2 °C
    resp = bytes.fromhex("12611a0cfc04f10cb105eb108800040c950651cb")
    req = _sess(b"\x21\x1a")
    ecu = FakeKLineEcu({req: resp})
    with Td5(KWP2000(KLine(ecu), tolerant=True)) as td5:
        vals = td5.read_lid(0x1A)
    assert round(vals["coolant_temp"], 1) == 59.2
