"""Airbag-felavkodning verifierad mot sniff 2026-08-10 (RDL 016)."""
from d2diag.airbag import decode_faults


def test_decode_captured_airbag_faults():
    # 61 02 90 04 90 16 00 00 … (belagt: fault 004 + 022, open circuit intermittent)
    data = bytes.fromhex("90 04 90 16 00 00 00 00 00 00".replace(" ", ""))
    faults = decode_faults(data)
    assert len(faults) == 2
    assert faults[0]["number"] == 4 and faults[0]["status"] == 0x90
    assert faults[1]["number"] == 0x16  # 22 → display 022
    assert "intermittent" in faults[0]["status_text"]


def test_empty_block_no_faults():
    assert decode_faults(bytes.fromhex("0000000000000000")) == []
