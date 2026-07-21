"""Td5 SecurityAccess seed→key.

Porterad från **td5keygen** (BSD-2-Clause):
    Copyright (c) 2017, paul@discotd5.com
    Python-variant: Copyright (c) 2017, xabiergarmendia@gmail.com
Se THIRD_PARTY_LICENSES.md i repo-roten för fullständig licenstext.

Algoritmen är en LFSR-variant härledd ur ECU-disassembly. C-originalet använder
XOR i tap-beräkningen, Python-originalet ``+``; de ger identiskt resultat eftersom
``(a + b + c + d) & 1 == a ^ b ^ c ^ d``. Ekvivalensen bevisas mot en ordagrann
referens över alla 65536 seeds i testerna.
"""
from __future__ import annotations


def key_from_seed(seed: int) -> int:
    """Beräkna 16-bitars nyckel ur 16-bitars seed."""
    if not 0 <= seed <= 0xFFFF:
        raise ValueError(f"seed utanför 16 bitar: {seed}")
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
    """Ta seed som två bytes, returnera nyckeln som två bytes (hög, låg)."""
    key = key_from_seed((seed_hi << 8) | seed_lo)
    return bytes([(key >> 8) & 0xFF, key & 0xFF])
