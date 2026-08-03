"""SLABS-lagret (Wabco ABS/SLS) — skelett.

SLABS nås via **5-baud slow init** (bara motorn använder fast init). Adress,
tjänstebytes och felminnesstruktur är ännu OKÄNDA — se modul-docstringen i
:mod:`d2diag.slabs.slabs`.
"""
from .slabs import KNOWN_SLABS_FAULTS, Slabs

__all__ = ["Slabs", "KNOWN_SLABS_FAULTS"]
