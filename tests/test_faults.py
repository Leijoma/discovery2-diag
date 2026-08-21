"""Tests for Td5 fault codes: read (21 3B), clear (31 DD) and bit decoding.

The protocol derived from the Ekaitza sniff (Read_Faults*.log).
"""
import d2diag.td5.faults as faults_mod
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Fault, Td5, decode_faults
from tests.fakes import FakeKLineEcu


def _sess(data: bytes) -> bytes:
    return encode(data, addressed=False)


def test_read_faults_raw_returns_status_block():
    block = bytes.fromhex("c0c00078087000")  # arbitrary status block
    req = _sess(b"\x21\x3b")
    resp = _sess(b"\x61\x3b" + block)
    ecu = FakeKLineEcu({req: resp})
    with Td5(KWP2000(KLine(ecu))) as td5:
        assert td5.read_faults_raw() == block


def test_clear_faults_sends_routine_dd_with_18_zeros():
    req = _sess(b"\x31\xdd" + b"\x00" * 18)
    resp = _sess(b"\x71\xdd")
    ecu = FakeKLineEcu({req: resp})
    with Td5(KWP2000(KLine(ecu))) as td5:
        td5.clear_faults()  # should not raise
    assert ecu.sent[0] == req  # exactly the right routine frame (31 DD + 18 zeros)


def test_decode_faults_reports_unknown_bits_generically():
    assert decode_faults(b"\x00" * 18) == []
    # offset 17 has no named bits in the map → set bits are reported generically
    block = bytearray(18)
    block[17] = 0x05
    assert set(decode_faults(bytes(block))) == {"byte17.bit0", "byte17.bit2"}


def test_decode_faults_named_bits_from_map(monkeypatch):
    monkeypatch.setattr(faults_mod, "FAULTS", [Fault(0, 0x80, "test-fel")])
    assert decode_faults(b"\x80") == ["test-fel"]
    # an unknown bit in the same byte does not disappear silently
    assert set(decode_faults(b"\xc0")) == {"test-fel", "byte0.bit6"}


def test_decode_faults_ignores_bytes_beyond_block():
    from d2diag.td5.faults import FAULT_BLOCK_LEN

    block = bytearray(FAULT_BLOCK_LEN + 3)
    block[FAULT_BLOCK_LEN] = 0xFF  # checksum/glitch after the block → should be ignored
    assert decode_faults(bytes(block)) == []


def test_decode_real_sniff_fault_block():
    # Real fault block from Ekaitza Read_Faults.log: 25 61 3b <35 bytes> <cksum>.
    resp = bytes.fromhex(
        "25613bc0c0000780870000701d000000ff00cf008f00003801008000280000000000000000001a"
    )
    block = resp[3 : 3 + 35]
    faults = decode_faults(block)
    named = [f for f in faults if not f.startswith("byte")]
    # offset 0 = 0xc0 → bit 0x40 + 0x80, Logged Low
    assert "air flow circuit (Logged Low)" in named
    assert "manifold pressure circuit (Logged Low)" in named
    # the coolant circuit set both stored (High, offset 3) and current (offset 5)
    assert "coolant temp. circuit (Logged High)" in named
    assert "coolant temp. circuit (Current)" in named
    assert "road speed missing (Logged)" in named
    assert "high speed crank (Logged)" in named
    assert len(named) == 32  # the whole block → 32 named faults
    # undefined bits are not dropped silently
    assert any(f.startswith("byte") for f in faults)
