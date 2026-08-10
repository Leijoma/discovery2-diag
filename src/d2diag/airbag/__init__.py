"""Airbag-lagret (TRW SPS Type 2A, SRS) — meny-data först.

🔴 Läs-endast domän (pyroteknik). Se `references/reference tool_master_menu.md` (Airbag)
och dicten (Airbag position=display-kod, 1–65).
"""
from .faults import decode_faults
from .menu import AIRBAG_MENU

__all__ = ["AIRBAG_MENU", "decode_faults"]
