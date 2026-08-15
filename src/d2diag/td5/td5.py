"""Td5-lagret: Td5-specifik logik ovanpå KWP2000.

Diagnostiksession, SecurityAccess (seed→key) och avläsning av identifiers med
skalning till fysiska värden (rpm, temperaturer, batterispänning, injektorbalans …).
Skalningen kommer från protokollreferensen — bör bekräftas mot bilen.
"""
from __future__ import annotations

import time
from typing import Callable

from ..session import EcuSession
from .identifiers import BY_NAME, LIDS, decode_lid
from .keygen import key_bytes_from_seed

TD5_DIAGNOSTIC_SESSION = 0xA0
_SECURITY_LEVEL_SEED = 0x01
_SECURITY_LEVEL_KEY = 0x02

# Felkoder: Td5 läser dem som ett statusblock via ReadDataByLocalIdentifier 0x3B
# (inte standard-DTC-tjänster) och raderar via StartRoutine 0xDD med 18 nollbytes.
# Härlett ur Ekaitza-sniffen (Read_Faults.log / Read_Faults_and_clear.log).
FAULT_LID = 0x3B
_CLEAR_FAULTS_ROUTINE = 0xDD
_CLEAR_FAULTS_PADDING = b"\x00" * 18

# Output-tester — BELAGT ur sniff 2026-08-08 (session.log, RDL 016). Nanacom
# pulsar TD5-utgångar via IOControl `30 <lid> ff`; wastegate/EGR tar PWM-parametrar.
# Injektorklick är StartRoutine `31 C2 0<n>`. Alla svarar `70/71 <id>` (ack, ingen data).
_OUTPUTS: "dict[str, tuple[int, bytes]]" = {
    "fuel_pump":   (0xA1, b"\xff"),
    "mil_lamp":    (0xA2, b"\xff"),
    "ac_clutch":   (0xA3, b"\xff"),
    "ac_fan":      (0xA4, b"\xff"),
    "glow_plugs":  (0xB3, b"\xff"),
    "rev_counter": (0xB7, b"\xff"),
    "temp_gauge":  (0xBA, b"\xff"),
    "egr_throttle": (0xBD, b"\xff\x00\xfa\x13\x88"),  # PWM-parametrar (duty/frekvens)
    "wastegate":   (0xBE, b"\xff\x00\x0a\x13\x88"),
}
_INJECTOR_ROUTINE = 0xC2       # `31 C2 0<n>` — pulsa injektor n (1–5)
_SECURITY_ROUTINE = 0xC0       # `31 C0` starta, `33 C0` läs status (03 = ej immobiliserad)

# Standardvärden för establish(): bus-idle innan init och antal helomförsök.
_DEFAULT_IDLE = 5.0
_DEFAULT_ATTEMPTS = 6


class Td5(EcuSession):
    name = "Td5"

    # livscykel (open/close/context) + read_block/tester_present ärvs från EcuSession

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
        unlock (via :meth:`connect`). Retryar hela sekvensen vid brus och
        returnerar C1-datafältet.

        Bäst mot en färsk ECU (tändningscykel precis innan). ``sleep`` injiceras
        för testbarhet. Höjer :class:`KWP2000Error` om det inte går efter
        ``attempts`` försök. En halvöppen session svarar ``7F`` på
        StartCommunication men går ändå att låsa upp — därför tolereras tom C1
        (se :meth:`EcuSession._establish`)."""
        return self._establish(
            after=self.connect, idle=idle, attempts=attempts, retry_sleep=8.0, sleep=sleep
        )

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

    # ---- felkoder ----------------------------------------------------- #
    def read_faults_raw(self) -> bytes:
        """Läs Td5:ans felstatusblock (rå bytes efter ``61 3B``) via 0x21 0x3B.

        Kräver upplåst session. Blocket är bitkodat; namngiven avkodning görs av
        :func:`d2diag.td5.faults.decode_faults`."""
        return self._kwp.read_local_identifier(FAULT_LID)

    def read_faults(self) -> "list[str]":
        """Läs och avkoda aktiva fel till en lista med beskrivningar."""
        from .faults import decode_faults

        return decode_faults(self.read_faults_raw())

    def clear_faults(self) -> None:
        """Radera lagrade felkoder (StartRoutine 0xDD). Kräver upplåst session."""
        self._kwp.start_routine(_CLEAR_FAULTS_ROUTINE, _CLEAR_FAULTS_PADDING)

    # ---- output-tester (kräver SÄNDANDE kabel) ------------------------ #
    def output_names(self) -> "list[str]":
        """Namn på de kända output-testerna (för UI/CLI)."""
        return list(_OUTPUTS)

    def output_test(self, name: str) -> None:
        """Pulsa en TD5-utgång (IOControl). ``name`` ur :meth:`output_names`.

        ⚠️ Aktivt test — kör bara stillastående, tändning på. Byte-exakt mot
        sniffen (t.ex. ``ac_clutch`` → ``30 A3 FF``)."""
        try:
            lid, params = _OUTPUTS[name]
        except KeyError:
            raise ValueError(f"okänd TD5-utgång: {name!r}") from None
        self._kwp.io_control(lid, params)

    def injector_pulse(self, cylinder: int) -> None:
        """Pulsa en injektor för hörbart klick (StartRoutine ``31 C2 0<n>``).

        ``cylinder`` 1–5. ⚠️ Aktivt test, motorn av."""
        if not 1 <= cylinder <= 5:
            raise ValueError("cylinder måste vara 1–5")
        self._kwp.start_routine(_INJECTOR_ROUTINE, bytes([cylinder]))

    # ---- immobiliser/security ----------------------------------------- #
    def security_status(self) -> int:
        """Läs immobiliser-status (`31 C0` starta + `33 C0` läs). Returnerar
        statusbyten — **0x03 = ej immobiliserad** (belagt RDL 016). Read-only.

        (Motsvarar Nanacoms 'GET SECURITY STATUS'. 'LEARN SECURITY CODE' är en
        annan, tillståndsändrande rutin och implementeras medvetet inte.)"""
        self._kwp.start_routine(_SECURITY_ROUTINE)
        result = self._kwp.request_routine_results(_SECURITY_ROUTINE)
        # svaret börjar med ekad rutin-id (C0), följt av statusbyte
        return result[1] if len(result) >= 2 else -1

    # bekvämlighet
    def rpm(self) -> float:
        return self.read("rpm")

    def coolant_temp(self) -> float:
        return self.read("coolant_temp")

    def battery_voltage(self) -> float:
        return self.read("battery")
