"""Td5 SecurityAccess seed→key.

Ported from **td5keygen** (BSD-2-Clause):
    Copyright (c) 2017, paul@discotd5.com
    Python variant: Copyright (c) 2017, xabiergarmendia@gmail.com
See THIRD_PARTY_LICENSES.md in the repo root for the full licence text.

The algorithm is an LFSR variant derived from ECU disassembly. The C original uses
XOR in the tap computation, the Python original ``+``; they give identical results because
``(a + b + c + d) & 1 == a ^ b ^ c ^ d``. The equivalence is proven against a verbatim
reference over all 65536 seeds in the tests.
"""
from __future__ import annotations


def key_from_seed(seed: int) -> int:
    """Compute a 16-bit key from a 16-bit seed."""
    if not 0 <= seed <= 0xFFFF:
        raise ValueError(f"seed outside 16 bits: {seed}")
    count = (
        (seed >> 0xC & 0x8)
        | (seed >> 0x5 & 0x4)
        | (seed >> 0x3 & 0x2)
        | (seed & 0x1)
    ) + 1
    for _ in range(count):
        tap = ((seed >> 1) ^ (seed >> 2) ^ (seed >> 8) ^ (seed >> 9)) & 1
        tmp = ((seed >> 1) | (tap << 0xF)) & 0xFFFF
        if (seed >> 0x3 & 1) and (seed >> 0xD & 1):
            seed = tmp & ~1
        else:
            seed = tmp | 1
    return seed & 0xFFFF


def key_bytes_from_seed(seed_hi: int, seed_lo: int) -> bytes:
    """Take the seed as two bytes, return the key as two bytes (high, low)."""
    key = key_from_seed((seed_hi << 8) | seed_lo)
    return bytes([(key >> 8) & 0xFF, key & 0xFF])
