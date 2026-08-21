"""BCU layer (Valeo, immobiliser/body electronics) — **read-only**.

Address 0x40 via 5-baud slow init (candidate, see :mod:`d2diag.bcu.bcu`), unaddressed
session, EKA code via ``21 CC``. Menu data in :mod:`d2diag.bcu.menu`.
"""
from .bcu import BCU_ADDRESS, EKA_LID, Bcu
from .menu import BCU_MENU

__all__ = ["BCU_MENU", "BCU_ADDRESS", "EKA_LID", "Bcu"]
