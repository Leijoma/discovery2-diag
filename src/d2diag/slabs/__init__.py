"""SLABS layer (Wabco ABS/SLS) — fast init 0x29, proven from sniffed reference tool traffic.

See ``references/slabs_protocol.md``. Connection: ``Slabs(KWP2000(KLine(transport,
target=0x29), tolerant=True))``.
"""
from .faults import SLABS_FAULT_BITS, decode_fault_block
from .slabs import SLABS_ADDRESS, Slabs

__all__ = ["Slabs", "SLABS_ADDRESS", "decode_fault_block", "SLABS_FAULT_BITS"]
