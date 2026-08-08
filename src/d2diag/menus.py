"""Modul-menyregister — driver dashboardens Karta-/täckningsflik.

Varje modul har en meny-lista (reference tool-meny + vår status), samma format som
:data:`d2diag.slabs.menu.SLABS_MENU`. Tomma listor = ännu ej dokumenterade (roadmap).
Uppdatera respektive ``*/menu.py`` under sniffning → Karta-fliken speglar det.
"""
from .bcu.menu import BCU_MENU
from .slabs.menu import SLABS_MENU

# Ordning = visningsordning i Karta-pickern.
MENUS: "dict[str, list]" = {
    "slabs": SLABS_MENU,
    "bcu": BCU_MENU,
    "ace": [],
    "autobox": [],
    "airbag": [],
}


def menu_for(module: str) -> "list":
    return MENUS.get(module, [])
