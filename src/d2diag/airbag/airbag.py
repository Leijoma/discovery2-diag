"""Airbag (TRW SPS 2A, SRS) modul-lager — **READ-ONLY, EXPERIMENTELLT**.

🔴 Pyroteknisk säkerhetsmodul. Detta lager **läser bara** felkoder (`21 02`).
Ingen clear, inga outputs, ingen SecurityAccess — medvetet inte implementerat.

Protokoll (härlett ur EN sniffad sekvens, `faultread-20260809.log` rad 1121–1122,
RDL 016 2026-08-10) — skiljer sig från Td5/SLABS:
  - **Adress 0x5B, 5-baud SLOW init** (`55`-sync), sedan **ADRESSERAD framing per
    meddelande** (`82 5b f7 …`), inte oadresserade sessionsramar.
  - **StartDiagnosticSession `10 81`** → `50 81` (session 0x81, ej Td5:ans 0xA0).
  - Felminne: **`21 02`** → `61 02` + poster `[status][fault-number]` (avkodas av
    :func:`decode_faults`). `21 01` sågs tomt.

⚠️ **Overifierat mot bilen av oss.** reference tool gjorde SecurityAccess (seed→key) FÖRE
läsningen; vi kan inte reproducera den (endast ett fångat par, ingen algoritm).
Om `21 02` KRÄVER upplåst session felar detta med negativt svar — då är airbag-
läsning blockerad tills algoritmen är känd. Läsning är ofarlig; misslyckas den
mjukt är det acceptabelt.
"""
from __future__ import annotations

import time
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000Error
from ..session import EcuSession
from .faults import FAULT_LID, decode_faults

AIRBAG_ADDRESS = 0x5B
_SESSION = 0x81            # StartDiagnosticSession-subfunktion (10 81 → 50 81)
_DEFAULT_ATTEMPTS = 3


class Airbag(EcuSession):
    """TRW SPS 2A via slow init 0x5B + adresserad framing. **Endast läsning.**

    Konstruera med ``KWP2000(KLine(transport, target=0x5B), tolerant=True,
    addressed=True)``. Livscykel/`read_local`/`read_block` ärvs från EcuSession.
    """

    name = "Airbag"

    def establish(
        self,
        *,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "tuple[int, int]":
        """5-baud slow init mot 0x5B → StartDiagnosticSession (10 81). Returnerar
        keybytes (KW1, KW2). Ingen SecurityAccess. Höjer :class:`KWP2000Error`
        efter ``attempts`` försök."""
        last: "Exception | None" = None
        for _ in range(attempts):
            try:
                kw = self._kwp.slow_init(AIRBAG_ADDRESS)
                self._kwp.start_diagnostic_session(_SESSION)
                return kw
            except (KLineError, KWP2000Error) as exc:
                last = exc
                sleep(2.0)  # låt bussen tystna före nästa slow-init-försök
        raise KWP2000Error(f"kunde inte etablera Airbag-session efter {attempts} försök: {last}")

    # ---- felkoder (ENDA skrivfria operationen) ------------------------- #
    def read_faults_raw(self) -> bytes:
        """Rå felminne (datafält efter ``61 02``) via `21 02`."""
        return self._kwp.read_local_identifier(FAULT_LID)

    def read_faults(self) -> "list[dict]":
        """Avkodade SRS-fel → ``[{number, status, status_text}]`` (se
        :func:`d2diag.airbag.faults.decode_faults`)."""
        return decode_faults(self.read_faults_raw())
