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

_DEFAULT_IDLE = 0.3    # bevisat stabilt värde (sniff 2026-08-07)
# MÄTT ur reference tool-sniffarna (2026-08-07/08/09, se slabs_protocol.md): VARJE
# lyckad SLABS-init kom på första försöket efter 25–28 s utan trafik mot modulen —
# 24.9, 26.5, 27.8, 28.0, 41.0, 51.5 s. Verktyget gjorde ALDRIG ett snabbt omförsök.
# Modulen behöver alltså en tyst period för att släppa sin länk, och varje init vi
# skickar under den nollställer väntan. Att hamra är därför aktivt skadligt: det är
# vad som höll oss ute i ~2 min 2026-08-18.
_DEFAULT_ATTEMPTS = 3
_DEFAULT_RETRY_SLEEP = 28.0
_CONFIRM_DELAY = 0.15  # paus mellan C1 och 1A 8A (reference tool: ~170 ms i sniffen)


class Slabs(EcuSession):
    """Wabco SLABS via fast init 0x29. Läs + rensa + ställdon.

    Livscykel (open/close/context), :meth:`read_block` och :meth:`tester_present`
    ärvs från :class:`EcuSession`."""

    name = "SLABS"
    _keepalive_sub = None  # SLABS vill ha bar 3E (sniffad ram 01 3e 3f), inte 3E 01

    # Växla adressläge mellan försöken. Funktionellt först eftersom de ramarna stod
    # för 6 träffar av 24 mot fysiskt 1 av 21 i bilen 2026-08-19 — MEN den siffran är
    # sammanblandad med försöksnumret: proben körde alltid varianterna i samma
    # ordning, och fysisk/F7 låg alltid först. Det kan alltså lika gärna vara att
    # första försöket väcker modulen och nästa kommer fram. Ordningen här är därför
    # en gissning som inte kostar något; det viktiga är att FLERA försök görs.
    _init_variants = ((True, 0xF1), (True, 0xF7), (False, None))

    def establish(
        self,
        *,
        idle: float = _DEFAULT_IDLE,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> bytes:
        """Bus-idle → tolerant fast init mot 0x29 (sök C1) → kvittens med `1A 8A`.

        Returnerar C1-datafältet (`57 8F`). Ingen session/unlock behövs
        (``after=None``). Höjer :class:`KWP2000Error` efter ``attempts`` försök.

        **`1A 8A` som första begäran speglar reference tool.** I varje lyckad init
        i sniffarna är verktygets första meddelande efter `C1` ett
        `02 1a 8a a6` → `5a 8a …`, ~170 ms senare, innan keepalive och läsningar
        börjar. Vi gör likadant och använder svaret som **kvittens på att sessionen
        verkligen lever** — vår toleranta init letar bara efter ett `C1` i bursten
        och kan i brus ge falskt positivt "session established" följt av noll
        läsningar (sett i bilen 2026-08-18). Misslyckad kvittens river INTE
        etableringen; den rapporteras via ``progress`` så anslutningsloggen visar
        skillnaden mellan "uppe" och "trodde vi var uppe".
        """
        c1 = self._establish(
            after=None, idle=idle, attempts=attempts, retry_sleep=_DEFAULT_RETRY_SLEEP,
            sleep=sleep, progress=progress,
        )
        self._confirm_session(sleep=sleep, progress=progress)
        return c1

    def _confirm_session(
        self,
        *,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> bool:
        """Skicka `1A 8A` som reference tool gör och rapportera utfallet. Best-effort."""
        sleep(_CONFIRM_DELAY)  # verktyget väntar ~170 ms efter C1 innan 1A 8A
        try:
            ident = self.read_ecu_id(ECU_ID_CONFIG)
        except Exception as exc:  # noqa: BLE001 — kvittensen får inte riva etableringen
            if progress:
                progress(f"no answer to 1A 8A ({type(exc).__name__}) — session may be dead")
            return False
        if progress:
            progress(f"session confirmed (1A 8A → {ident[:6].hex(' ')}…)")
        return True

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
