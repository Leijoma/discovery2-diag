"""SLABS-lagret verifierat mot VERKLIG sniffad reference tool-trafik (2026-08-07).

Varje förfrågan/svar nedan är exakta bytes ur ``references/captures/
slabs_session_20260807.log``. Testerna bevisar att vårt lager:
  - **skriver** byte-identiska kommandon (clear + ställdon), och
  - **läser/avkodar** SLABS-svaren rätt (felblock, VIN, versioner).
"""
import pytest

from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.slabs import Slabs, decode_fault_block
from tests.fakes import FakeKLineEcu


def _frame(data: bytes) -> bytes:
    return encode(data, addressed=False)  # oadresserad session-ram <len><data><cs>


def _slabs(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, Slabs(KWP2000(KLine(ecu)))


# ---- avkodningen matchar fångade frames exakt --------------------------- #
def test_capture_frames_are_wellformed():
    # Bekräftar att vår oadresserade kodning ger EXAKT de sniffade byten.
    assert _frame(b"\x21\x11").hex(" ") == "02 21 11 34"
    assert _frame(b"\x14\xff\xff").hex(" ") == "03 14 ff ff 15"
    assert _frame(b"\x31\x31\x0a").hex(" ") == "03 31 31 0a 6f"
    assert _frame(b"\x31\x2f\x28").hex(" ") == "03 31 2f 28 8b"
    assert _frame(b"\x31\x30\x28").hex(" ") == "03 31 30 28 8c"
    assert _frame(b"\x31\x25\x08\xfa").hex(" ") == "04 31 25 08 fa 5c"


# ---- LÄSA: felblock avkodas mot baslinjen ------------------------------- #
def test_decode_logged_fault_block_matches_baseline():
    # 21 11 före clear: byte3.bit4 + byte10.bit4 = fel 020 (RF-givare) + 027 (shuttle)
    block = bytes.fromhex("00 00 00 10 00 00 00 00 00 00 10 00 00 00 00 00".replace(" ", ""))
    faults = decode_fault_block(block)
    assert any(f.startswith("020:") for f in faults)
    assert any(f.startswith("027:") for f in faults)
    assert len(faults) == 2


def test_read_faults_logged_and_current():
    logged = bytes.fromhex("00000010000000000000100000000000")
    responses = {
        _frame(b"\x21\x11"): _frame(b"\x61\x11" + logged),
        _frame(b"\x21\x47"): _frame(b"\x61\x47" + bytes(16)),  # aktuella = inga
    }
    ecu, slabs = _slabs(responses)
    with slabs:
        faults = slabs.read_faults()
    assert len(faults["loggade"]) == 2
    assert faults["aktuella"] == []


def test_cleared_block_gives_no_faults():
    responses = {
        _frame(b"\x21\x11"): _frame(b"\x61\x11" + bytes(16)),
        _frame(b"\x21\x47"): _frame(b"\x61\x47" + bytes(16)),
    }
    ecu, slabs = _slabs(responses)
    with slabs:
        assert slabs.read_faults() == {"loggade": [], "aktuella": []}


# ---- LÄSA: ECU-identitet ------------------------------------------------ #
def test_read_vin():
    vin = b"SALLXXXXXXXXXXXXX"
    responses = {_frame(b"\x1a\x8d"): _frame(b"\x5a\x8d" + vin)}
    ecu, slabs = _slabs(responses)
    with slabs:
        assert slabs.read_vin() == "SALLXXXXXXXXXXXXX"


def test_read_software_versions():
    data = b"KRTE49B0\x0030303030\x00HDTE16A0"
    responses = {_frame(b"\x1a\x8b"): _frame(b"\x5a\x8b" + data)}
    ecu, slabs = _slabs(responses)
    with slabs:
        vers = slabs.read_software_versions()
    assert "KRTE49B0" in vers and "HDTE16A0" in vers


# ---- SKRIVA: kommandon blir byte-identiska med reference toolens --------------- #
def test_clear_faults_sends_exact_capture():
    responses = {_frame(b"\x14\xff\xff"): _frame(b"\x54")}
    ecu, slabs = _slabs(responses)
    with slabs:
        slabs.clear_faults()
    assert ecu.sent[-1] == bytes.fromhex("0314ffff15")  # '03 14 ff ff 15'


@pytest.mark.parametrize("call, frame_hex", [
    (lambda s: s.buzzer(),               "03 31 31 0a 6f"),
    (lambda s: s.compressor(),           "03 31 30 28 8c"),
    (lambda s: s.exhaust_valve(),        "03 31 2f 28 8b"),
    (lambda s: s.pump_relay(True),       "04 31 25 08 fa 5c"),
    (lambda s: s.raise_corner("left"),   "03 31 33 28 8f"),
    (lambda s: s.lower_corner("right"),  "03 31 36 28 92"),
])
def test_actuator_command_matches_capture(call, frame_hex):
    want = bytes.fromhex(frame_hex.replace(" ", ""))
    rid = want[2]
    responses = {want: _frame(bytes([0x71, rid, 0x20]))}
    ecu, slabs = _slabs(responses)
    with slabs:
        call(slabs)
    assert ecu.sent[-1] == want
