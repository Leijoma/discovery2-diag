"""Delad ECU-sessionsbas för modul-lagren (Td5, Slabs, …).

Samlar det som varje modul-lager gör likadant ovanpå :class:`KWP2000`:
livscykel (open/close/context), keepalive, rå LID-läsning och den toleranta
fast-init-retryn i :meth:`_establish`. Modulklasserna ärver detta och lägger
bara till sitt egna: Td5 en session + SecurityAccess-unlock (``after=connect``),
Slabs ingenting (``after=None``).

:meth:`read_block` är primitiven som kopplar en live-session till
``sniff.automap`` — den returnerar exakt ``{lid_hex: bytes}``-formen automap
väntar sig, så en differential-mappning kan läsa en LID-uppsättning direkt.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

from .kline.kline import KLineError
from .kwp2000.kwp2000 import KWP2000, KWP2000Error


class EcuSession:
    """Gemensam bas för ett modul-lager ovanpå KWP2000.

    Subklasser sätter :attr:`name` och anropar :meth:`_establish` från sin egen
    ``establish`` (Td5 med ``after=self.connect``, Slabs med ``after=None``).
    """

    name: str = "ECU"
    _keepalive_sub: "int | None" = 0x01  # TesterPresent-sub; SLABS överrider → None (bar 3E)

    def __init__(self, kwp: KWP2000) -> None:
        self._kwp = kwp

    # ---- livscykel (delegeras hela vägen ner till transporten) --------- #
    def open(self) -> None:
        self._kwp.open()

    def close(self) -> None:
        self._kwp.close()

    def __enter__(self) -> "EcuSession":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- rå läsning ---------------------------------------------------- #
    def read_local(self, lid: int) -> bytes:
        """Rå ReadDataByLocalIdentifier (``21 xx``) — datafält efter ekad LID."""
        return self._kwp.read_local_identifier(lid)

    def read_block(self, lids: "Iterable[int]") -> "dict[str, bytes]":
        """Läs en uppsättning LID:er → ``{lid_hex: bytes}`` (automap-format).

        En LID som felar hoppas tyst över (bussbrus/ej stödd på denna modul), så
        en differential-läsning aldrig kraschar mitt i. Nyckeln är gemena 2-hex
        (``0x1c`` → ``"1c"``) — samma form ``sniff.automap`` indexerar ``raws`` med.
        """
        out: "dict[str, bytes]" = {}
        for lid in lids:
            try:
                out[f"{lid:02x}"] = self.read_local(lid)
            except (KWP2000Error, KLineError):
                pass
        return out

    def tester_present(self) -> None:
        """Keepalive (``3E`` → ``7E``) — håll sessionen vid liv mellan förfrågningar."""
        self._kwp.tester_present(self._keepalive_sub)

    # ---- etablering ---------------------------------------------------- #
    def _establish(
        self,
        after: "Callable[[], None] | None" = None,
        *,
        idle: float,
        attempts: int,
        retry_sleep: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bytes:
        """Bus-idle → tolerant fast init (sök C1) → valfri efter-fas (``after``).

        Retryar hela sekvensen ``attempts`` gånger vid brus. Returnerar C1-datafältet.

        ``after`` kör en modul-specifik uppföljning efter lyckad init (Td5:
        session + unlock). Är den satt tolereras en misslyckad init (C1 = tom) —
        en halvöppen session från ett tidigare försök svarar ``7F`` på
        StartCommunication men går ändå att använda direkt. Är ``after`` ``None``
        (Slabs) måste init lyckas rent innan vi returnerar.

        ``sleep`` injiceras för testbarhet. Höjer :class:`KWP2000Error` efter
        ``attempts`` misslyckade försök.
        """
        sleep(idle)  # låt linjen vara tyst så en ev. öppen session hinner dö
        last: "Exception | None" = None
        for _ in range(attempts):
            try:
                c1 = self._kwp.start_communication(tolerant=True)
            except (KLineError, KWP2000Error) as exc:
                last = exc
                if after is None:
                    sleep(retry_sleep)
                    continue
                c1 = b""  # sessionen kan redan vara öppen — prova after ändå
            if after is None:
                return c1
            try:
                after()
                return c1
            except (KWP2000Error, KLineError, ValueError) as exc:
                last = exc
                sleep(retry_sleep)  # låt sessionen dö före nästa init
        raise KWP2000Error(
            f"kunde inte etablera {self.name}-session efter {attempts} försök: {last}"
        )
