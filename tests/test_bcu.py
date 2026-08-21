"""BCU-lagret — slow init 0x40, identifiering och EKA-läsning (`21 CC`).

Allt mot FakeKLineEcu; ingen hårdvara. Underlaget för ramarna kommer från
sniffen 2026-08-09 (`logs/faultread-20260809-2.log`) — se d2diag.bcu.bcu.
"""
import pytest

from d2diag.bcu import BCU_ADDRESS, Bcu
from d2diag.bcu.bcu import _plausible
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000, KWP2000Error
from tests.fakes import FakeKLineEcu


def _f(d):
    return encode(d, addressed=False)


def _bcu(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, Bcu(KWP2000(KLine(ecu, target=BCU_ADDRESS, timeout=0.05), tolerant=True))


def test_establish_does_slow_init_on_0x40():
    ecu, bcu = _bcu({})
    with bcu:
        kw = bcu.establish(sleep=lambda *_: None)
    assert ecu.slow_init_addr == BCU_ADDRESS      # 5-baud, inte fast init
    assert kw == (0xE9, 0x8F)                     # fakens keybytes


def test_establish_raises_after_attempts_when_silent():
    class _Silent(FakeKLineEcu):
        def slow_init(self, address):
            return b""                            # ingen 0x55-sync

    ecu = _Silent({})
    bcu = Bcu(KWP2000(KLine(ecu, target=BCU_ADDRESS, timeout=0.05), tolerant=True))
    msgs = []
    with bcu:
        with pytest.raises(KWP2000Error):
            bcu.establish(attempts=2, sleep=lambda *_: None, progress=msgs.append)
    assert sum("inget svar" in m for m in msgs) == 2


def test_read_eka_uses_lid_cc():
    # `02 21 CC EF` är den ram reference tool skickade under markören "read set eka".
    ecu, bcu = _bcu({_f(b"\x21\xcc"): _f(b"\x61\xcc\x07\x02\x08\x06")})
    with bcu:
        eka = bcu.read_eka()
    assert _f(b"\x21\xcc") in ecu.sent
    assert eka["bytes"] == [7, 2, 8, 6]
    # Tolerant läsning returnerar bursten från SID:en och framåt, alltså med
    # checksumman kvar på slutet — samma beteende som Td5/SLABS. Tolkningarna
    # skivar de fyra första byten, så det stör inte.
    assert eka["raw"].startswith(b"\x07\x02\x08\x06")


def test_identify_collects_the_options_that_answer():
    ecu, bcu = _bcu({_f(b"\x1a\x8a"): _f(b"\x5a\x8a" + b"YWC001234")})
    with bcu:
        ident = bcu.identify()
    assert ident["8a"].startswith(b"YWC001234")
    assert "80" not in ident            # tysta optioner utelämnas, inte krasch


def test_plausible_picks_the_interpretation_that_fits_1_to_16():
    # EKA är fyra siffror, var och en 1–16. Formatet är inte belagt, så tolkningen
    # ska pekas ut av vilka värden som ligger i intervallet.
    assert _plausible([7, 2, 8, 6], [0, 7, 0, 2]) == "bytes"       # nibbles har 0
    assert _plausible([0x72, 0x86, 0, 0], [7, 2, 8, 6]) == "nibbles"
    assert _plausible([99, 0, 0, 0], [9, 9, 0, 0]) == "ingen — formatet är något annat"


def test_find_digits_identifies_the_encoding_with_a_known_code():
    # Med facit behöver formatet inte gissas: sök den kända koden i råsvaret.
    # Koden skickas in av anroparen och lagras aldrig i repot (publikt).
    from d2diag.bcu.bcu import find_digits
    code = [1, 2, 3, 4]  # FAKE code — the real EKA is never stored in this repo

    one_per_byte = bytes.fromhex("61 cc 01 02 03 04 4a")
    assert find_digits(one_per_byte, code) == {
        "encoding": "bytes", "offset": 2, "bytes": "01 02 03 04"}

    packed = bytes.fromhex("61 cc 12 34 00 4a")
    assert find_digits(packed, code) == {
        "encoding": "nibbles", "offset": 2, "bytes": "12 34"}

    assert find_digits(bytes.fromhex("61 cc de ad be ef"), code) is None
