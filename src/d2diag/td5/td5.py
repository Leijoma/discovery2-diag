"""Td5-lagret: Td5-specifik logik ovanpå KWP2000.

Just nu: diagnostiksession och SecurityAccess (seed→key). Identifiers och
datakonvertering (rpm, kylvätsketemp, injektorbalans …) läggs till när vi kan
verifiera skalningen mot en riktig ECU.
"""
from __future__ import annotations

from ..kwp2000.kwp2000 import KWP2000
from .keygen import key_bytes_from_seed

TD5_DIAGNOSTIC_SESSION = 0xA0
_SECURITY_LEVEL_SEED = 0x01
_SECURITY_LEVEL_KEY = 0x02


class Td5:
    def __init__(self, kwp: KWP2000) -> None:
        self._kwp = kwp

    # livscykel delegeras hela vägen ner till transporten
    def open(self) -> None:
        self._kwp.open()

    def close(self) -> None:
        self._kwp.close()

    def __enter__(self) -> "Td5":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start_session(self) -> bytes:
        """StartDiagnosticSession i Td5:ans diagnostikläge (0xA0)."""
        return self._kwp.start_diagnostic_session(TD5_DIAGNOSTIC_SESSION)

    def unlock(self) -> None:
        """SecurityAccess: hämta seed, räkna nyckel, skicka nyckel."""
        seed = self._kwp.request_seed(_SECURITY_LEVEL_SEED)
        if len(seed) < 2:
            raise ValueError(f"oväntad seed-längd: {seed.hex(' ')}")
        key = key_bytes_from_seed(seed[0], seed[1])
        self._kwp.send_key(key, _SECURITY_LEVEL_KEY)
