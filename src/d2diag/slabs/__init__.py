"""SLABS-lagret (Wabco ABS/SLS) — fast init 0x29, belagt ur sniffad reference tool-trafik.

Se ``references/slabs_protocol.md``. Uppkoppling: ``Slabs(KWP2000(KLine(transport,
target=0x29), tolerant=True))``.
"""
from .faults import SLABS_FAULT_BITS, decode_fault_block
from .slabs import SLABS_ADDRESS, Slabs

__all__ = ["Slabs", "SLABS_ADDRESS", "decode_fault_block", "SLABS_FAULT_BITS"]
