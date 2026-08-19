"""BCU-lagret (Valeo, immobiliser/centralelektronik) — **read-only**.

Adress 0x40 via 5-baud slow init (kandidat, se :mod:`d2diag.bcu.bcu`), oadresserad
session, EKA-kod via ``21 CC``. Menydata i :mod:`d2diag.bcu.menu`.
"""
from .bcu import BCU_ADDRESS, EKA_LID, Bcu
from .menu import BCU_MENU

__all__ = ["BCU_MENU", "BCU_ADDRESS", "EKA_LID", "Bcu"]
