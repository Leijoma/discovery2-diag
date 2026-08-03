"""Tester för sniff-kärnan: ram-uppdelning på gap + annotering."""
from d2diag.sniff import describe, frame_by_gaps


def test_frame_by_gaps_splits_on_silence():
    samples = [
        (0.000, 0x02), (0.001, 0x10), (0.002, 0xA0), (0.003, 0xB2),  # meddelande 1
        (0.100, 0x01), (0.101, 0x50), (0.102, 0x51),                  # meddelande 2 efter gap
    ]
    msgs = frame_by_gaps(samples, gap=0.01)
    assert len(msgs) == 2
    assert msgs[0]["data"] == b"\x02\x10\xa0\xb2"
    assert msgs[1]["data"] == b"\x01\x50\x51"
    assert msgs[0]["gap_before"] is None
    assert abs(msgs[1]["gap_before"] - 0.097) < 1e-6


def test_frame_by_gaps_single_message_when_no_gap():
    samples = [(i * 0.001, 0x00) for i in range(5)]
    msgs = frame_by_gaps(samples, gap=0.01)
    assert len(msgs) == 1
    assert len(msgs[0]["data"]) == 5


def test_describe_requests_and_responses():
    assert describe(b"\x81\x13\xf7\x81\x0c") == "REQ StartCommunication"
    assert describe(b"\x03\xc1\x57\x8f\xaa") == "StartCommunication positivt (C1)"
    assert describe(b"\x02\x10\xa0\xb2") == "REQ StartDiagnosticSession"
    assert describe(b"\x01\x50\x51") == "SVAR StartDiagnosticSession"
    assert describe(b"\x04\x61\x09\x00\x00\x6e") == "SVAR ReadDataByLocalId"


def test_describe_negative_and_sync():
    assert describe(b"\x03\x7f\x10\x10\xa2") == "NEG på StartDiagnosticSession (NRC 0x10)"
    assert describe(b"\x55\x8f\xea") == "slow-init sync (0x55)"
    assert describe(b"") == ""
