"""Airbag-lagret (TRW SPS Type 2A, SRS) — meny-data först.

🔴 Läs-endast domän (pyroteknik). Se `references/reference_tool_master_menu.md` (Airbag)
och dicten (Airbag position=display-kod, 1–65).
"""
from .airbag import AIRBAG_ADDRESS, Airbag
from .faults import decode_faults
from .menu import AIRBAG_MENU

__all__ = ["AIRBAG_ADDRESS", "AIRBAG_MENU", "Airbag", "decode_faults"]
