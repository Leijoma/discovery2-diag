"""BCU-lagret (Valeo, immobiliser/centralelektronik) — meny-data först.

Protokoll-lagret byggs efter BCU-sniff (EKA + market/DRL). Se
``references/bcu_sniff_plan.md`` och ``references/reference_tool_master_menu.md``.
"""
from .menu import BCU_MENU

__all__ = ["BCU_MENU"]
