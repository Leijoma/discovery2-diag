"""Td5-lagret: Td5-specifik logik ovanpå KWP2000.

Diagnostiksession, SecurityAccess (seed→key) och avläsning av identifiers med
skalning till fysiska värden (rpm, temperaturer, batterispänning, injektorbalans …).
Skalningen kommer från protokollreferensen — bör bekräftas mot bilen.
"""
from __future__ import annotations

from ..kwp2000.kwp2000 import KWP2000
from .identifiers import BY_NAME, LIDS, decode_lid
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

    # ---- avläsning av livedata --------------------------------------- #
    def read_lid(self, lid: int) -> "dict[str, float]":
        """Läs en identifier (21 xx) och avkoda alla signaler i den."""
        return decode_lid(lid, self._kwp.read_local_identifier(lid))

    def read(self, name: str) -> float:
        """Läs en enskild signal per namn, t.ex. 'rpm' eller 'coolant_temp'."""
        return self.read_lid(BY_NAME[name].lid)[name]

    def read_all(self) -> "dict[str, float]":
        """Läs alla kända LID:er → {signalnamn: värde}. En LID som felar hoppas över."""
        out: "dict[str, float]" = {}
        for lid in LIDS:
            try:
                out.update(self.read_lid(lid))
            except Exception:  # noqa: BLE001
                pass
        return out

    # bekvämlighet
    def rpm(self) -> float:
        return self.read("rpm")

    def coolant_temp(self) -> float:
        return self.read("coolant_temp")

    def battery_voltage(self) -> float:
        return self.read("battery")
