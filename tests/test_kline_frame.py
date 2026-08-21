"""Tests for frame encoding/decoding — both addressed and unaddressed formats."""
import pytest

from d2diag.kline.frame import (
    ChecksumError,
    FrameError,
    checksum,
    decode,
    encode,
)


def test_checksum_is_8bit_sum():
    assert checksum(b"\x81\x13\xf7\x81") == 0x0C


def test_addressed_known_vector():
    # StartCommunication to the Td5 ECU (fast init)
    assert encode(b"\x81", target=0x13, source=0xF7, addressed=True) == bytes.fromhex("8113F7810C")


def test_nonaddressed_known_vectors():
    # session frames: StartDiagnosticSession and seed request
    assert encode(b"\x10\xa0") == bytes.fromhex("0210A0B2")
    assert encode(b"\x27\x01") == bytes.fromhex("0227012A")


def test_decode_addressed():
    d = decode(bytes.fromhex("8113F7810C"))
    assert (d.data, d.target, d.source) == (b"\x81", 0x13, 0xF7)
    assert d.addressed


def test_decode_nonaddressed():
    d = decode(bytes.fromhex("0210A0B2"))
    assert d.data == b"\x10\xa0"
    assert d.target is None
    assert not d.addressed


def test_roundtrip_both_modes():
    for addressed in (True, False):
        frame = encode(b"\x21\x09", addressed=addressed)
        assert decode(frame).data == b"\x21\x09"


def test_long_nonaddressed_uses_length_byte():
    data = bytes(range(70))  # > 0x3F
    frame = encode(data)
    assert frame[0] == 0x00  # format 0, length follows
    assert frame[1] == 70
    assert decode(frame).data == data


def test_bad_checksum_raises():
    frame = bytearray(encode(b"\x81"))
    frame[-1] ^= 0xFF
    with pytest.raises(ChecksumError):
        decode(bytes(frame))


def test_empty_payload_raises():
    with pytest.raises(FrameError):
        encode(b"")
