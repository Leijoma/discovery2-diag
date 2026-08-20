"""BCU-lagret (Valeo centralelektronik / immobiliser) — **read-only**.

Underlaget kommer från två håll:

* **Adress `0x40`, 5-BAUD SLOW INIT — BEKRÄFTAT i bilen 2026-08-20.** Handskakning
  med KWP2000-nycklar ``E5 8F`` (som adressjakten 2026-08-05 förutsade). Uppkoppling
  på första försöket efter tändningscykel.
* ⚠️ **EKA är LÅST bakom SecurityAccess.** Utan ``27 01``/``27 02`` returnerar BCU:n
  en fast platshållare (``11 99 07 01…``) på BÅDE ``1A xx`` och ``21 CC`` — bevisat
  i bilen: alla ReadEcuId-optioner + EKA-läsningen gav identisk data. Reference tool
  gör SecurityAccess DIREKT efter uppkoppling (sniff 2026-08-09), före varje läsning.
  Valeo seed→key-algoritmen är **okänd** (till skillnad från Td5:ans, som är portad),
  så vi kan fånga en seed men inte låsa upp än. ``identify`` är därför inte pålitlig
  förrän unlock finns.
* **Sessionen** ur sniffen ``logs/faultread-20260809-2.log``: oadresserade
  längdramar, keepalive ``02 3E 01 41`` (med sub-byte, till skillnad från SLABS),
  och ReadDataByLocalIdentifier. **EKA-koden läses med `21 CC`** — den ramen
  skickades exakt en gång, direkt under operatörsmarkören "read set eka".

⚠️ **Endast läsning.** BCU:n får aldrig kodas eller skrivas blint: en låst BCU
kan enligt communityn inte låsas upp med diagnostikmetoder (brick-risk). Ingen
nyckelprogrammering, inga settings-skrivningar, inga ställdon här.

BCU:n går in i diagnostikläge vid en **tändningsövergång** — reference tool ber
operatören slå av tändningen, trycka en tangent, och sedan slå på den igen.
"""
from __future__ import annotations

import time
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000Error
from ..session import EcuSession

BCU_ADDRESS = 0x40          # kandidat, se modul-docstring
EKA_LID = 0xCC              # `21 CC` — belagt ur sniffen 2026-08-09
_DEFAULT_ATTEMPTS = 3


class Bcu(EcuSession):
    """Valeo BCU via 5-baud slow init. Läser EKA-kod och ECU-identifiering.

    Konstruera med ``KWP2000(KLine(transport, target=BCU_ADDRESS), tolerant=True)``
    — sessionen är OADRESSERAD (till skillnad från airbagen).
    """

    name = "BCU"
    # Keepalive med sub-byte: sniffen visar `02 3e 01 41`, inte SLABS bara `3E`.
    _keepalive_sub = 0x01

    def establish(
        self,
        *,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> "tuple[int, int]":
        """5-baud slow init mot 0x40. Returnerar keybytes (KW1, KW2).

        Ingen StartDiagnosticSession och ingen SecurityAccess — sniffen visar att
        reference tool gör SecurityAccess senare i sessionen, men om `21 CC` kräver
        det vet vi inte. Prova läsningen först; ett ``securityAccessDenied`` (NRC
        0x33) är i sig ett svar värt att få.
        """
        last: "Exception | None" = None
        for i in range(attempts):
            if progress:
                progress(f"5-baud slow init mot 0x{BCU_ADDRESS:02X} (försök {i+1}/{attempts})")
            try:
                kw = self._kwp.slow_init(BCU_ADDRESS)
                if progress:
                    progress(f"handskakning klar, keybytes {kw[0]:02X} {kw[1]:02X}")
                return kw
            except (KLineError, KWP2000Error) as exc:
                last = exc
                if progress:
                    progress(f"inget svar ({type(exc).__name__})")
                sleep(2.0)  # låt bussen tystna före nästa försök
        raise KWP2000Error(
            f"kunde inte etablera BCU-session efter {attempts} försök: {last}")

    # ---- identitet ----------------------------------------------------- #
    def identify(self, options: "tuple[int, ...]" = (0x80, 0x8A, 0x8B, 0x8D, 0x9B)) -> "dict":
        """Fråga modulen vem den är: ``1A xx`` för ett antal optioner.

        Returnerar ``{option_hex: bytes}`` för dem som svarar. Är detta BCU:n bör
        något av svaren innehålla läsbar ASCII (delnummer/mjukvaruversion) — det
        är så vi avgör om 0x40-gissningen håller.
        """
        out: "dict[str, bytes]" = {}
        for opt in options:
            try:
                out[f"{opt:02x}"] = self._kwp.request(0x1A, bytes([opt]))[1:]
            except (KWP2000Error, KLineError):
                pass
        return out

    # ---- EKA ----------------------------------------------------------- #
    def read_eka_raw(self) -> bytes:
        """Rå ``21 CC`` — datafältet utan ekad LID."""
        return self.read_local(EKA_LID)

    def read_eka(self) -> "dict":
        """Läs EKA-koden. Returnerar råbytes + tolkningskandidater.

        Formatet är **inte belagt** — sniffens svar på `21 CC` var trasigt (KKL:n
        som passiv tapp lastade bussen). Vi vet bara att koden är **fyra siffror,
        var och en 1–16** (`references/valeo_bcu_capabilities.md`). Därför
        returneras råbytes plus de två rimliga tolkningarna, så de kan jämföras
        mot en känd kod i stället för att gissa:

        * ``bytes`` — en siffra per byte (de fyra första)
        * ``nibbles`` — två siffror per byte (hög/låg nibble)
        """
        raw = self.read_eka_raw()   # OBS: tolerant läsning tar med checksumman
        as_bytes = [b for b in raw[:4]]
        nibbles = []
        for b in raw[:2]:
            nibbles += [b >> 4, b & 0x0F]
        return {"raw": raw, "bytes": as_bytes, "nibbles": nibbles,
                "plausible": _plausible(as_bytes, nibbles)}


def find_digits(raw: bytes, digits: "list[int]") -> "dict | None":
    """Sök en KÄND fyrsiffrig kod i ett rått svar och returnera hur den är kodad.

    Med facit i hand behöver formatet inte gissas. Vi provar de kodningar som är
    rimliga för en kod där varje siffra är 1–16, och söker på alla offset — svaret
    kan ha huvud-bytes före själva koden:

    * ``bytes``   — en siffra per byte, t.ex. ``XX XX XX XX``
    * ``nibbles`` — två siffror per byte (BCD-liknande), t.ex. ``79 86``

    Returnerar ``{"encoding": …, "offset": …}`` eller ``None``. Koden skickas in
    av anroparen; den lagras aldrig i repot (publikt) — se ``tools/bcu_probe.py``.
    """
    as_bytes = bytes(digits)
    if len(digits) % 2 == 0:
        packed = bytes((digits[i] << 4) | digits[i + 1] for i in range(0, len(digits), 2))
    else:
        packed = b""
    for name, needle in (("bytes", as_bytes), ("nibbles", packed)):
        if needle:
            i = raw.find(needle)
            if i >= 0:
                return {"encoding": name, "offset": i, "bytes": needle.hex(" ")}
    return None


def _plausible(as_bytes: "list[int]", nibbles: "list[int]") -> str:
    """Vilken tolkning ger fyra siffror i det giltiga intervallet 1–16?"""
    ok_b = len(as_bytes) == 4 and all(1 <= d <= 16 for d in as_bytes)
    ok_n = len(nibbles) == 4 and all(1 <= d <= 16 for d in nibbles)
    if ok_b and not ok_n:
        return "bytes"
    if ok_n and not ok_b:
        return "nibbles"
    if ok_b and ok_n:
        return "båda (jämför mot känd kod)"
    return "ingen — formatet är något annat"
