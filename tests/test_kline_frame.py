"""Tester för ramkodning/-avkodning och checksumma."""
import pytest

from d2diag.kline.frame import (
    TD5_ECU_ADDRESS,
    TESTER_ADDRESS,
    ChecksumError,
    FrameError,
    checksum,
    decode,
    encode,
)


def test_checksum_is_8bit_sum():
    assert checksum(b"\x81\x13\xf7\x81") == 0x0C


def test_encode_known_vector():
    # StartCommunication till Td5-ECU:n
    assert encode(b"\x81", target=0x13, source=0xF7) == bytes.fromhex("8113F7810C")


def test_encode_decode_roundtrip():
    frame = encode(b"\x21\x09", target=TD5_ECU_ADDRESS, source=TESTER_ADDRESS)
    d = decode(frame)
    assert (d.target, d.source, d.data) == (TD5_ECU_ADDRESS, TESTER_ADDRESS, b"\x21\x09")


def test_long_payload_uses_separate_length_byte():
    data = bytes(range(64))  # 64 > 0x3F
    frame = encode(data)
    assert frame[0] == 0x80  # längd 0 i formatbyten
    assert frame[3] == 64    # separat längdbyte
    assert decode(frame).data == data


def test_bad_checksum_raises():
    frame = bytearray(encode(b"\x81"))
    frame[-1] ^= 0xFF
    with pytest.raises(ChecksumError):
        decode(bytes(frame))


def test_empty_payload_raises():
    with pytest.raises(FrameError):
        encode(b"")


def test_too_short_frame_raises():
    with pytest.raises(FrameError):
        decode(b"\x81\x13\xf7")
