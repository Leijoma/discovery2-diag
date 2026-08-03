"""Tester för Td5-felkoder: läsning (21 3B), radering (31 DD) och bitavkodning.

Protokollet härlett ur Ekaitza-sniffen (Read_Faults*.log).
"""
import d2diag.td5.faults as faults_mod
from d2diag.kline import KLine, encode
from d2diag.kwp2000 import KWP2000
from d2diag.td5 import Fault, Td5, decode_faults
from tests.fakes import FakeKLineEcu


def _sess(data: bytes) -> bytes:
    return encode(data, addressed=False)


def test_read_faults_raw_returns_status_block():
    block = bytes.fromhex("c0c00078087000")  # godtyckligt statusblock
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
        td5.clear_faults()  # ska inte höja
    assert ecu.sent[0] == req  # exakt rätt rutinram (31 DD + 18 nollor)


def test_decode_faults_reports_unknown_bits_generically():
    assert decode_faults(b"\x00" * 18) == []
    # offset 17 saknar namngivna bitar i kartan → satta bitar rapporteras generiskt
    block = bytearray(18)
    block[17] = 0x05
    assert set(decode_faults(bytes(block))) == {"byte17.bit0", "byte17.bit2"}


def test_decode_faults_named_bits_from_map(monkeypatch):
    monkeypatch.setattr(faults_mod, "FAULTS", [Fault(0, 0x80, "test-fel")])
    assert decode_faults(b"\x80") == ["test-fel"]
    # okänd bit i samma byte försvinner inte tyst
    assert set(decode_faults(b"\xc0")) == {"test-fel", "byte0.bit6"}


def test_decode_faults_ignores_bytes_beyond_block():
    from d2diag.td5.faults import FAULT_BLOCK_LEN

    block = bytearray(FAULT_BLOCK_LEN + 3)
    block[FAULT_BLOCK_LEN] = 0xFF  # checksumma/glitch efter blocket → ska ignoreras
    assert decode_faults(bytes(block)) == []


def test_decode_real_sniff_fault_block():
    # Verkligt felblock ur Ekaitza Read_Faults.log: 25 61 3b <35 bytes> <cksum>.
    resp = bytes.fromhex(
        "25613bc0c0000780870000701d000000ff00cf008f00003801008000280000000000000000001a"
    )
    block = resp[3 : 3 + 35]
    faults = decode_faults(block)
    named = [f for f in faults if not f.startswith("byte")]
    # offset 0 = 0xc0 → bit 0x40 + 0x80, Logged Low
    assert "air flow circuit (Logged Low)" in named
    assert "manifold pressure circuit (Logged Low)" in named
    # coolant-kretsen tänd både lagrat (High, offset 3) och aktuellt (offset 5)
    assert "coolant temp. circuit (Logged High)" in named
    assert "coolant temp. circuit (Current)" in named
    assert "road speed missing (Logged)" in named
    assert "high speed crank (Logged)" in named
    assert len(named) == 32  # hela blocket → 32 namngivna fel
    # odefinierade bitar tappas inte tyst
    assert any(f.startswith("byte") for f in faults)
