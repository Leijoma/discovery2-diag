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
    # Har modulen en StartDiagnosticSession att avsluta rent? Td5 → True; SLABS och
    # Airbag kör tjänsterna direkt efter init och har ingen session att stänga.
    _has_session: bool = False

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

    # ---- ren avslutning (delad buss) ----------------------------------- #
    def end_session(self) -> None:
        """Avsluta diagnostiksessionen rent (StopDiagnosticSession, ``20`` → ``60``).

        **Best-effort** — K-line är en DELAD buss och ECU:n håller sessionen öppen
        tills den timeoutar av sig själv. En kvarlämnad TD5-session får nästa
        moduls StartCommunication att svara ``7F 81 10`` (generalReject), vilket
        är roten till trög SLABS-anslutning efter modulbyte. Ett misslyckat
        ``20`` (redan död session, tyst buss) är därför inte ett fel: vi stänger
        ändå. Moduler utan session (``_has_session = False``) gör ingenting.
        """
        if self._has_session:
            try:
                self._kwp.stop_diagnostic_session()
            except Exception:  # noqa: BLE001 — sessionen kan redan vara borta
                pass
        self._stop_communication()

    def _stop_communication(self) -> None:
        """StopCommunication (``82``) — best-effort, gäller ALLA moduler.

        Fast init upprättar en kommunikationslänk även för moduler utan
        diagnostiksession. Stänger vi bara serieporten lever länken kvar i ECU:n
        och nästa StartCommunication möts av ``7F 81 10`` — även från en HELT NY
        process (belagt i bilen 2026-08-18: färsk process, SLABS som första modul,
        generalReject på första försöket).
        """
        try:
            self._kwp.stop_communication()
        except Exception:  # noqa: BLE001 — ingen länk öppen är det normala
            pass

    def release(self) -> None:
        """:meth:`end_session` + :meth:`close` — vid modulbyte OCH på felvägar.

        Även när sessionen verkar död måste länken rivas: en tappad läsning
        betyder inte att ECU:n glömt oss. Loggen 2026-08-18 visar mönstret — tre
        tomma pollar → close() utan ``82`` → varje följande init möts av
        ``7F 81 10`` i ~90 s. Kostar ~0,5 s mot en tyst buss (kort burst,
        ingen omsändning), vilket är en bråkdel av en misslyckad reconnect.
        """
        self.end_session()
        self.close()

    # ---- etablering ---------------------------------------------------- #
    def _establish(
        self,
        after: "Callable[[], None] | None" = None,
        *,
        idle: float,
        attempts: int,
        retry_sleep: float,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> bytes:
        """Bus-idle → tolerant fast init (sök C1) → valfri efter-fas (``after``).

        Retryar hela sekvensen ``attempts`` gånger vid brus. Returnerar C1-datafältet.

        ⚠️ ``retry_sleep`` är en **tyst period**, inte en artighetspaus. Mätt över
        alla reference tool-sniffar (2026-08-07/08/09): varje lyckad SLABS-init kom
        på FÖRSTA försöket efter 25–28 s utan trafik mot modulen, och verktyget
        gjorde aldrig ett snabbt omförsök. Att skicka något alls under pausen —
        inklusive ett ``82`` — nollställer väntan.

        ``after`` kör en modul-specifik uppföljning efter lyckad init (Td5:
        session + unlock). Är den satt tolereras en misslyckad init (C1 = tom) —
        en halvöppen session från ett tidigare försök svarar ``7F`` på
        StartCommunication men går ändå att använda direkt. Är ``after`` ``None``
        (Slabs) måste init lyckas rent innan vi returnerar.

        ``sleep`` injiceras för testbarhet. Höjer :class:`KWP2000Error` efter
        ``attempts`` misslyckade försök.
        """
        def _say(msg: str) -> None:
            if progress is not None:
                progress(msg)

        # Riv en ev. kvarlämnad länk EN gång, innan tystnaden — inte mellan försöken.
        # En modul som fortfarande har en öppen session svarar 7F 81 10 på en annan
        # moduls init (belagt i sniffen 2026-08-08: TD5:s keepalive 2,9 s före ett
        # SLABS-init, och TD5 barkar generalReject medan SLABS svarar C1).
        _say("clearing any stale link")
        self._stop_communication()
        _say("waiting for the bus to settle")
        sleep(idle)  # låt linjen vara tyst så en ev. öppen session hinner dö
        last: "Exception | None" = None
        for i in range(attempts):
            _say(f"sending init (try {i + 1}/{attempts})")
            try:
                c1 = self._kwp.start_communication(tolerant=True)
            except (KLineError, KWP2000Error) as exc:
                last = exc
                if after is None:
                    # Ta med bursten i loggen — annars syns den bara på SISTA
                    # försöket och man ser inte om rejecten fanns redan från start.
                    _say(f"no response yet ({exc})")
                    if i + 1 < attempts:
                        # TYST paus — inte "vänta lite och försök igen fort". Modulen
                        # behöver en tyst period för att släppa sin länk; varje byte
                        # vi skickar under den nollställer väntan. Se _establish-docen.
                        _say(f"quiet period: {retry_sleep:.0f}s before next try")
                    sleep(retry_sleep)
                    continue
                c1 = b""  # sessionen kan redan vara öppen — prova after ändå
            if after is None:
                _say("session established")
                return c1
            try:
                _say("response received, unlocking")
                after()
                _say("session established")
                return c1
            except (KWP2000Error, KLineError, ValueError) as exc:
                last = exc
                _say(f"unlock failed, retrying (try {i + 1}/{attempts})")
                sleep(retry_sleep)  # låt sessionen dö före nästa init
        raise KWP2000Error(
            f"kunde inte etablera {self.name}-session efter {attempts} försök: {last}"
        )
