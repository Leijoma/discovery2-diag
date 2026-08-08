"""Modul-menyregister — driver dashboardens Karta-/täckningsflik.

Varje modul har en meny-lista (reference tool-meny + vår status), samma format som
:data:`d2diag.slabs.menu.SLABS_MENU`. Tomma listor = ännu ej dokumenterade (roadmap).
Uppdatera respektive ``*/menu.py`` under sniffning → Karta-fliken speglar det.
"""
from .ace.menu import ACE_MENU
from .airbag.menu import AIRBAG_MENU
from .autobox.menu import AUTOBOX_MENU
from .bcu.menu import BCU_MENU
from .slabs.menu import SLABS_MENU
from .td5.menu import TD5_MENU

# Ordning = visningsordning i Karta-pickern.
MENUS: "dict[str, list]" = {
    "td5": TD5_MENU,
    "slabs": SLABS_MENU,
    "bcu": BCU_MENU,
    "ace": ACE_MENU,
    "autobox": AUTOBOX_MENU,
    "airbag": AIRBAG_MENU,
}


def menu_for(module: str) -> "list":
    return MENUS.get(module, [])
