"""Tests for Td5 seed→key.

The proof: my port (XOR/OR) is compared against a verbatim transcription of the
original's ``+`` form over ALL 65536 seeds. If they match everywhere, the port is
provably equivalent to the reference implementation.
"""
import pytest

from d2diag.td5.keygen import key_bytes_from_seed, key_from_seed


def _reference_plus(seed: int) -> int:
    # Verbatim transcription of keytool.py (paul@discotd5.com, BSD-2), with '+'.
    count = ((seed >> 0xC & 0x8) + (seed >> 0x5 & 0x4) + (seed >> 0x3 & 0x2) + (seed & 0x1)) + 1
    for _ in range(count):
        tap = ((seed >> 1) + (seed >> 2) + (seed >> 8) + (seed >> 9)) & 1
        tmp = (seed >> 1) | (tap << 0xF)
        if (seed >> 0x3 & 1) and (seed >> 0xD & 1):
            seed = tmp & ~1
        else:
            seed = tmp | 1
    return seed


def test_matches_reference_over_all_seeds():
    for s in range(0x10000):
        assert key_from_seed(s) == _reference_plus(s), f"skillnad vid seed {s:#06x}"


def test_seed_range_is_validated():
    with pytest.raises(ValueError):
        key_from_seed(-1)
    with pytest.raises(ValueError):
        key_from_seed(0x10000)


def test_key_bytes_split_matches_int():
    key = key_from_seed(0x1234)
    assert key_bytes_from_seed(0x12, 0x34) == bytes([key >> 8, key & 0xFF])
