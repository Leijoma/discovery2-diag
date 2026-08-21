"""Airbag fault decoding verified against sniff 2026-08-10 (RDL 016)."""
from d2diag.airbag import AIRBAG_ADDRESS, Airbag, decode_faults
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from tests.fakes import FakeKLineEcu


def test_decode_captured_airbag_faults():
    # 61 02 90 04 90 16 00 00 … (proven: fault 004 + 022, open circuit intermittent)
    data = bytes.fromhex("90 04 90 16 00 00 00 00 00 00".replace(" ", ""))
    faults = decode_faults(data)
    assert len(faults) == 2
    assert faults[0]["number"] == 4 and faults[0]["status"] == 0x90
    assert faults[1]["number"] == 0x16  # 22 → display 022
    assert "intermittent" in faults[0]["status_text"]


def test_empty_block_no_faults():
    assert decode_faults(bytes.fromhex("0000000000000000")) == []


def _areq(data):
    return encode(data, AIRBAG_ADDRESS, 0xF7, addressed=True)   # tester → airbag


def _aresp(data):
    return encode(data, 0xF7, AIRBAG_ADDRESS, addressed=True)   # airbag → tester


def _airbag(responses):
    ecu = FakeKLineEcu(responses)
    ab = Airbag(KWP2000(KLine(ecu, target=AIRBAG_ADDRESS), tolerant=True, addressed=True))
    return ecu, ab


def test_airbag_establish_slow_init_then_session():
    # slow init 0x5B → keywords; StartDiagnosticSession 10 81 → 50 81 (addressed)
    ecu, ab = _airbag({_areq(b"\x10\x81"): _aresp(b"\x50\x81")})
    with ab:
        kw = ab.establish()
    assert kw == (0xE9, 0x8F)                 # KW1/KW2 from the fake's slow-init
    assert ecu.slow_init_addr == AIRBAG_ADDRESS


def test_airbag_read_faults_decodes_004_022():
    # 21 02 → 61 02 90 04 90 16 … (proven from the sniff), addressed framing
    resp = {
        _areq(b"\x10\x81"): _aresp(b"\x50\x81"),
        _areq(b"\x21\x02"): _aresp(b"\x61\x02\x90\x04\x90\x16" + bytes(8)),
    }
    ecu, ab = _airbag(resp)
    with ab:
        ab.establish()
        faults = ab.read_faults()
    assert {f["number"] for f in faults} == {4, 0x16}
    # verify that we ACTUALLY sent addressed frames (82 5b f7 …)
    assert any(bytes(s).startswith(b"\x82\x5b\xf7") for s in ecu.sent)


def test_airbag_is_read_only():
    # Safety invariant: the airbag layer exposes no clear/output/security.
    for attr in ("clear_faults", "output_test", "start_routine", "unlock", "buzzer"):
        assert not hasattr(Airbag, attr), f"Airbag must NOT have {attr} (pyro safety)"
