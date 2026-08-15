"""Wabco SLABS (ABS + självnivellerande luftfjädring) modul-lager.

Protokollet är **belagt ur sniffad reference tool-trafik 2026-08-07** (se
``references/slabs_protocol.md`` + rålogg ``references/captures/``). Till skillnad
från Td5 krävs **ingen StartDiagnosticSession och ingen SecurityAccess** — efter
fast init går man direkt på tjänsterna.

  - **Adress 0x29**, FAST init: `81 29 F7 81 22` → `C1 57 8F` (KWP2000, KW2=8F).
  - Oadresserade längd-ramar (`02 21 47 …`), keepalive `3E`→`7E`.
  - Felkoder: `21 11` (loggade) / `21 47` (aktuella), 16-byte bit-per-fel; clear = `14 FF FF`.
  - Live-data: `21 xx`. Ställdon/tester: `31 xx` (StartRoutine).

Kräver **tändning PÅ** (tändningsmatad). Comms dör >8–20 km/h → kör stillastående.
"""
from __future__ import annotations

import time
from typing import Callable

from ..session import EcuSession
from .faults import FAULT_BLOCK_LEN, decode_fault_block

SLABS_ADDRESS = 0x29

# ReadEcuIdentification-optioner (1A xx)
ECU_ID_CONFIG = 0x8A
ECU_ID_VERSIONS = 0x8B
ECU_ID_VIN = 0x8D

# Felminne
LOGGED_FAULTS_LID = 0x11   # 21 11
CURRENT_FAULTS_LID = 0x47  # 21 47
CLEAR_FAULTS_SERVICE = 0x14  # 14 FF FF → 54

# StartRoutine-identifierare (31 xx), belagda ur sniffen
RID_PUMP_RELAY = 0x25
RID_EXHAUST_VALVE = 0x2F
RID_COMPRESSOR = 0x30
RID_BUZZER = 0x31
RID_RAISE_LEFT = 0x33
RID_RAISE_RIGHT = 0x34
RID_LOWER_LEFT = 0x35
RID_LOWER_RIGHT = 0x36
RID_ABS_TEST = 0x22  # bleed + hjultester; sub-byte väljer krets

# ABS_TEST-subkommandon (byte efter 0x22)
ABS_SUB_POWER_BLEED = 0x04
ABS_SUB_FRONT_RIGHT = 0x10
ABS_SUB_FRONT_LEFT = 0x11
ABS_SUB_REAR_RIGHT = 0x12
ABS_SUB_REAR_LEFT = 0x13

_DEFAULT_IDLE = 0.3
_DEFAULT_ATTEMPTS = 3


class Slabs(EcuSession):
    """Wabco SLABS via fast init 0x29. Läs + rensa + ställdon.

    Livscykel (open/close/context), :meth:`read_block` och :meth:`tester_present`
    ärvs från :class:`EcuSession`."""

    name = "SLABS"

    def establish(
        self,
        *,
        idle: float = _DEFAULT_IDLE,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bytes:
        """Bus-idle → tolerant fast init mot 0x29 (sök C1). Returnerar C1-datafältet
        (`57 8F`). Ingen session/unlock behövs (``after=None``). Höjer
        :class:`KWP2000Error` efter ``attempts`` försök.
        """
        return self._establish(
            after=None, idle=idle, attempts=attempts, retry_sleep=5.0, sleep=sleep
        )

    # ---- ECU-identitet (1A xx) --------------------------------------- #
    def read_ecu_id(self, option: int) -> bytes:
        """ReadEcuIdentification. Returnerar datafältet (utan ekad option-byte)."""
        return self._kwp.request(0x1A, bytes([option]))[1:]

    def read_vin(self) -> str:
        return self.read_ecu_id(ECU_ID_VIN).split(b"\x00", 1)[0].decode("ascii", "replace").strip()

    def read_software_versions(self) -> "list[str]":
        raw = self.read_ecu_id(ECU_ID_VERSIONS)
        return [p.decode("ascii", "replace") for p in raw.split(b"\x00") if p]

    # ---- felkoder ----------------------------------------------------- #
    def _fault_block(self, lid: int) -> bytes:
        return self._kwp.read_local_identifier(lid)[:FAULT_BLOCK_LEN]

    def read_logged_faults_raw(self) -> bytes:
        return self._fault_block(LOGGED_FAULTS_LID)

    def read_current_faults_raw(self) -> bytes:
        return self._fault_block(CURRENT_FAULTS_LID)

    def read_faults(self) -> "dict[str, list[str]]":
        """Avkodade felkoder: {"loggade": [...], "aktuella": [...]}."""
        return {
            "loggade": decode_fault_block(self.read_logged_faults_raw()),
            "aktuella": decode_fault_block(self.read_current_faults_raw()),
        }

    def clear_faults(self) -> None:
        """ClearDiagnosticInformation (14 FF FF). Nollställer felminnet."""
        self._kwp.request(CLEAR_FAULTS_SERVICE, b"\xff\xff")

    # ---- live-data (21 xx) ------------------------------------------- #
    def read_data(self, lid: int) -> bytes:
        """Rå ReadDataByLocalIdentifier (21 xx). Datafält utan ekad LID."""
        return self._kwp.read_local_identifier(lid)

    # ---- ställdon / tester (31 xx) ----------------------------------- #
    # ⚠️ Alla dessa RÖR HÅRDVARA. Kör stillastående, tändning på.
    def start_routine(self, rid: int, params: bytes = b"") -> bytes:
        """Generisk StartRoutine (31 xx). Returnerar svaret (börjar med ekad RID)."""
        return self._kwp.start_routine(rid, params)

    def buzzer(self) -> None:
        """⚠️ SLS-summer på (ofarligt, hörbart — bra skriv-verifiering)."""
        self.start_routine(RID_BUZZER, b"\x0a")

    def compressor(self) -> None:
        """⚠️ SLS-kompressor."""
        self.start_routine(RID_COMPRESSOR, b"\x28")

    def exhaust_valve(self) -> None:
        """⚠️ SLS avluftningsventil."""
        self.start_routine(RID_EXHAUST_VALVE, b"\x28")

    def pump_relay(self, on: bool = True) -> None:
        """⚠️ ABS-pumprelä. Param `08 fa`/`02 fa` belagd ur sniff (on/off preliminär;
        avslutande byte i loggen = checksumma, ej param)."""
        self.start_routine(RID_PUMP_RELAY, b"\x08\xfa" if on else b"\x02\xfa")

    def raise_corner(self, side: str) -> None:
        """⚠️ Höj luftfjädring. side ∈ {'left','right'}."""
        self.start_routine(RID_RAISE_LEFT if side == "left" else RID_RAISE_RIGHT, b"\x28")

    def lower_corner(self, side: str) -> None:
        """⚠️ Sänk luftfjädring. side ∈ {'left','right'}."""
        self.start_routine(RID_LOWER_LEFT if side == "left" else RID_LOWER_RIGHT, b"\x28")

    # Hjul → (sub, ventilmask). Belagt ur sniff: 2 bitar/hjul i ordning HF,VF,HB,VB.
    _WHEEL = {
        "fr": (0x10, 0x03), "fl": (0x11, 0x0c),
        "rr": (0x12, 0x30), "rl": (0x13, 0xc0),
    }

    def wheel_test(self, corner: str) -> None:
        """⚠️ ABS-ventiltest på ETT hjul. corner ∈ {'fl','fr','rl','rr'}.
        `31 22 <sub> <mask> c1 f4` + 8 nollbyte (belagt ur sniff)."""
        sub, mask = self._WHEEL[corner]
        self.start_routine(RID_ABS_TEST, bytes([sub, mask, 0xc1, 0xf4]) + bytes(8))
