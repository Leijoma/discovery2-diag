"""TD5 layer verified against REAL sniffed reference tool traffic (2026-08-08, RDL 016).

Exact bytes from ``logs/session.log`` (the TD5 session). Proves that our layer:
  - computes the correct SecurityAccess key (seed→key),
  - decodes the `21 3B` fault block correctly, and
  - **writes byte-identical** output/injector/security commands.
"""
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Td5
from d2diag.td5.faults import decode_faults
from d2diag.td5.keygen import key_bytes_from_seed
from tests.fakes import FakeKLineEcu


def _frame(data: bytes) -> bytes:
    return encode(data, addressed=False)  # unaddressed frame <len><data><cs>


def _td5(responses):
    ecu = FakeKLineEcu(responses)
    return ecu, Td5(KWP2000(KLine(ecu)))


# ---- SecurityAccess: seed d3 e6 → key ad 87 (captured) ------------------ #
def test_keygen_matches_capture():
    assert key_bytes_from_seed(0xD3, 0xE6) == bytes([0xAD, 0x87])


# ---- fault block 21 3B (engine, warm idle) ------------------------------ #
def test_fault_block_decode_matches_capture():
    block = bytes.fromhex(
        "40 00 00 01 40 00 00 00 00 00 00 00 00 00 00 00 00 00"
        "44 00 40 00 00 00 20 00 00 00 20 00 00 00 00 00 00".replace(" ", "")
    )
    faults = decode_faults(block)
    assert "air flow circuit (Current)" in faults
    assert "air flow circuit (Logged Low)" in faults
    assert "inlet air temp. circuit (Logged High)" in faults
    assert "can tx/rx error (Logged)" in faults
    assert "problem detected with drive demand (Current)" in faults


# ---- output tests: byte-identical commands ------------------------------ #
# (sent frame → response) exactly from session.log
_OUTPUT_CAPTURE = {
    "fuel_pump":   ("03 30 a1 ff d3", "02 70 a1 13"),
    "mil_lamp":    ("03 30 a2 ff d4", "02 70 a2 14"),
    "ac_clutch":   ("03 30 a3 ff d5", "02 70 a3 15"),
    "ac_fan":      ("03 30 a4 ff d6", "02 70 a4 16"),
    "glow_plugs":  ("03 30 b3 ff e5", "02 70 b3 25"),
    "rev_counter": ("03 30 b7 ff e9", "02 70 b7 29"),
    "temp_gauge":  ("03 30 ba ff ec", "02 70 ba 2c"),
    "egr_throttle": ("07 30 bd ff 00 fa 13 88 88", "02 70 bd 2f"),
    "wastegate":   ("07 30 be ff 00 0a 13 88 99", "02 70 be 30"),
}


def test_output_tests_send_exact_bytes():
    for name, (sent_hex, resp_hex) in _OUTPUT_CAPTURE.items():
        sent = bytes.fromhex(sent_hex.replace(" ", ""))
        resp = bytes.fromhex(resp_hex.replace(" ", ""))
        ecu = FakeKLineEcu({sent: resp})
        Td5(KWP2000(KLine(ecu))).output_test(name)
        assert ecu.sent[-1] == sent, f"{name}: {ecu.sent[-1].hex(' ')} != {sent_hex}"


def test_injector_pulse_sends_exact_bytes():
    ecu, td5 = _td5({_frame(b"\x31\xc2\x01"): _frame(b"\x71\xc2")})
    td5.injector_pulse(1)
    assert ecu.sent[-1].hex(" ") == "03 31 c2 01 f7"


def test_security_status_reads_not_immobilised():
    ecu, td5 = _td5({
        _frame(b"\x31\xc0"): _frame(b"\x71\xc0"),
        _frame(b"\x33\xc0"): _frame(b"\x73\xc0\x03"),
    })
    assert td5.security_status() == 0x03  # 0x03 = not immobilised (capture)
    assert ecu.sent[0].hex(" ") == "02 31 c0 f3"
    assert ecu.sent[1].hex(" ") == "02 33 c0 f5"
