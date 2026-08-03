"""Td5-lagret: Td5-specifik logik ovanpå KWP2000.

Diagnostiksession, SecurityAccess (seed→key) och avläsning av identifiers med
skalning till fysiska värden (rpm, temperaturer, batterispänning, injektorbalans …).
Skalningen kommer från protokollreferensen — bör bekräftas mot bilen.
"""
from __future__ import annotations

import time
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000, KWP2000Error
from .identifiers import BY_NAME, LIDS, decode_lid
from .keygen import key_bytes_from_seed

TD5_DIAGNOSTIC_SESSION = 0xA0
_SECURITY_LEVEL_SEED = 0x01
_SECURITY_LEVEL_KEY = 0x02

# Standardvärden för establish(): bus-idle innan init och antal helomförsök.
_DEFAULT_IDLE = 5.0
_DEFAULT_ATTEMPTS = 6


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

    def connect(self) -> None:
        """StartDiagnosticSession + SecurityAccess-unlock.

        Förutsätter etablerad kommunikation (fast init redan gjord). Efter detta
        är ECU:n upplåst och ``21 xx``-läsning fungerar."""
        self.start_session()
        self.unlock()

    def establish(
        self,
        *,
        idle: float = _DEFAULT_IDLE,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bytes:
        """Full uppkoppling: bus-idle → tolerant fast init (sök C1) → session →
        unlock. Retryar hela sekvensen vid brus och returnerar C1-datafältet.

        Bäst mot en färsk ECU (tändningscykel precis innan). ``sleep`` injiceras
        för testbarhet. Höjer :class:`KWP2000Error` om det inte går efter
        ``attempts`` försök.

        En halvöppen session från ett tidigare försök svarar ``7F`` på
        StartCommunication; därför en längre paus mellan försök så den hinner
        timeouta innan nästa init.
        """
        sleep(idle)  # låt linjen vara tyst så ev. öppen session dör
        last: "Exception | None" = None
        for _ in range(attempts):
            try:
                c1 = self._kwp.start_communication(tolerant=True)
            except KLineError as exc:
                last = exc
                sleep(1.0)
                continue
            try:
                self.connect()
                return c1
            except (KWP2000Error, KLineError, ValueError) as exc:
                last = exc
                sleep(8.0)
        raise KWP2000Error(f"kunde inte etablera Td5-session efter {attempts} försök: {last}")

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
