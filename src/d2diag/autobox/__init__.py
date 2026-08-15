"""Autobox-lagret (Bosch GS8.87.0 / ZF4HP22-24 automatlåda) — meny-data först.

Protokoll-lagret byggs efter EAT-sniff (gick ej läsa med reference tool 1). Se
`references/reference_tool_master_menu.md` (Auto Gearbox) och dicten (39 P-koder).
"""
from .menu import AUTOBOX_MENU

__all__ = ["AUTOBOX_MENU"]
