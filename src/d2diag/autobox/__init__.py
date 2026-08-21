"""Autobox layer (Bosch GS8.87.0 / ZF4HP22-24 automatic gearbox) — menu data first.

The protocol layer is built after an EAT sniff (could not be read with reference tool 1). See
`references/reference_tool_master_menu.md` (Auto Gearbox) and the dictionary (39 P-codes).
"""
from .menu import AUTOBOX_MENU

__all__ = ["AUTOBOX_MENU"]
