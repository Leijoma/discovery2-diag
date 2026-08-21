"""Shared ECU session base for the module layers (Td5, Slabs, …).

Collects what every module layer does the same way on top of :class:`KWP2000`:
lifecycle (open/close/context), keepalive, raw LID reads and the tolerant
fast-init retry in :meth:`_establish`. The module classes inherit this and add
only their own: Td5 a session + SecurityAccess unlock (``after=connect``),
Slabs nothing (``after=None``).

:meth:`read_block` is the primitive that connects a live session to
``sniff.automap`` — it returns exactly the ``{lid_hex: bytes}`` shape automap
expects, so a differential mapping can read a set of LIDs directly.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

from .kline.kline import KLineError
from .kwp2000.kwp2000 import KWP2000, KWP2000Error


class EcuSession:
    """Common base for a module layer on top of KWP2000.

    Subclasses set :attr:`name` and call :meth:`_establish` from their own
    ``establish`` (Td5 with ``after=self.connect``, Slabs with ``after=None``).
    """

    name: str = "ECU"
    _keepalive_sub: "int | None" = 0x01  # TesterPresent sub; SLABS overrides → None (bare 3E)
    # Does the module have a StartDiagnosticSession to close cleanly? Td5 → True; SLABS and
    # Airbag run the services right after init and have no session to close.
    _has_session: bool = False
    # Init variants to cycle through between attempts: (functional, source address).
    # Default is physical addressing with tester address 0xF7 (like the reference tool).
    # Modules can add more — see Slabs.
    _init_variants: "tuple" = ((False, None),)
    # P4 (inter-byte time when sending) in seconds. 0.0 = the whole frame in one sweep, as
    # we have always done. Set per module and applied to KLine in :meth:`open`.
    _write_gap: float = 0.0

    def __init__(self, kwp: KWP2000) -> None:
        self._kwp = kwp

    # ---- lifecycle (delegated all the way down to the transport) ------- #
    def open(self) -> None:
        kline = getattr(self._kwp, "_k", None)
        if kline is not None and self._write_gap:
            kline.write_gap = self._write_gap
        self._kwp.open()

    def close(self) -> None:
        self._kwp.close()

    def __enter__(self) -> "EcuSession":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- raw read ------------------------------------------------------ #
    def read_local(self, lid: int) -> bytes:
        """Raw ReadDataByLocalIdentifier (``21 xx``) — data field after the echoed LID."""
        return self._kwp.read_local_identifier(lid)

    def read_block(self, lids: "Iterable[int]") -> "dict[str, bytes]":
        """Read a set of LIDs → ``{lid_hex: bytes}`` (automap format).

        A LID that fails is silently skipped (bus noise/not supported on this module), so
        a differential read never crashes midway. The key is lowercase 2-hex
        (``0x1c`` → ``"1c"``) — the same form ``sniff.automap`` indexes ``raws`` by.
        """
        out: "dict[str, bytes]" = {}
        for lid in lids:
            try:
                out[f"{lid:02x}"] = self.read_local(lid)
            except (KWP2000Error, KLineError):
                pass
        return out

    def tester_present(self) -> None:
        """Keepalive (``3E`` → ``7E``) — keep the session alive between requests."""
        self._kwp.tester_present(self._keepalive_sub)

    # ---- clean teardown (shared bus) ----------------------------------- #
    def end_session(self) -> None:
        """End the diagnostic session cleanly (StopDiagnosticSession, ``20`` → ``60``).

        **Best-effort** — K-line is a SHARED bus and the ECU keeps the session open
        until it times out on its own. A left-over TD5 session makes the next
        module's StartCommunication answer ``7F 81 10`` (generalReject), which
        is the root of slow SLABS connection after a module switch. A failed
        ``20`` (already-dead session, silent bus) is therefore not an error: we close
        anyway. Modules without a session (``_has_session = False``) do nothing.
        """
        if self._has_session:
            try:
                self._kwp.stop_diagnostic_session()
            except Exception:  # noqa: BLE001 — the session may already be gone
                pass
        self._stop_communication()

    def _stop_communication(self) -> None:
        """StopCommunication (``82``) — best-effort, applies to ALL modules.

        Fast init establishes a communication link even for modules without a
        diagnostic session. If we just close the serial port the link lives on in the ECU
        and the next StartCommunication is met with ``7F 81 10`` — even from a BRAND-NEW
        process (proven in the car 2026-08-18: fresh process, SLABS as first module,
        generalReject on the first attempt).
        """
        try:
            self._kwp.stop_communication()
        except Exception:  # noqa: BLE001 — no open link is the normal case
            pass

    def release(self) -> None:
        """:meth:`end_session` + :meth:`close` — on module switch AND on error paths.

        Even when the session seems dead the link must be torn down: a dropped read
        does not mean the ECU has forgotten us. The 2026-08-18 log shows the pattern — three
        empty polls → close() without ``82`` → every following init met with
        ``7F 81 10`` for ~90 s. Costs ~0.5 s against a silent bus (short burst,
        no retransmit), which is a fraction of a failed reconnect.
        """
        self.end_session()
        self.close()

    # ---- establishment ------------------------------------------------- #
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
        """Bus-idle → tolerant fast init (search for C1) → optional after-phase (``after``).

        Retries the whole sequence ``attempts`` times on noise. Returns the C1 data field.

        ⚠️ ``retry_sleep`` is a **quiet period**, not a politeness pause. Measured across
        all reference tool sniffs (2026-08-07/08/09): every successful SLABS init came
        on the FIRST attempt after 25–28 s with no traffic to the module, and the tool
        never made a quick retry. Sending anything at all during the pause —
        including an ``82`` — resets the wait.

        ``after`` runs a module-specific follow-up after successful init (Td5:
        session + unlock). If it is set a failed init is tolerated (C1 = empty) —
        a half-open session from an earlier attempt answers ``7F`` to
        StartCommunication but can still be used directly. If ``after`` is ``None``
        (Slabs) init must succeed cleanly before we return.

        ``sleep`` is injected for testability. Raises :class:`KWP2000Error` after
        ``attempts`` failed attempts.
        """
        def _say(msg: str) -> None:
            if progress is not None:
                progress(msg)

        # Tear down any left-over link ONCE, before the silence — not between attempts.
        # A module that still has an open session answers 7F 81 10 to another
        # module's init (proven in the sniff 2026-08-08: TD5's keepalive 2.9 s before a
        # SLABS init, and TD5 barks generalReject while SLABS answers C1).
        _say("clearing any stale link")
        self._stop_communication()
        _say("waiting for the bus to settle")
        sleep(idle)  # let the line stay quiet so any open session has time to die
        last: "Exception | None" = None
        for i in range(attempts):
            functional, source = self._init_variants[i % len(self._init_variants)]
            how = "" if not functional else " [funktionell, F1]"
            _say(f"sending init (try {i + 1}/{attempts}){how}")
            try:
                c1 = self._kwp.start_communication(
                    tolerant=True, functional=functional, source=source)
            except (KLineError, KWP2000Error) as exc:
                last = exc
                if after is None:
                    # Include the burst in the log — otherwise it only shows on the LAST
                    # attempt and you can't see whether the reject was there from the start.
                    _say(f"no response yet ({exc})")
                    if i + 1 < attempts:
                        # QUIET pause — not "wait a bit and retry quickly". The module
                        # needs a quiet period to release its link; every byte
                        # we send during it resets the wait. See the _establish docstring.
                        _say(f"quiet period: {retry_sleep:.0f}s before next try")
                    sleep(retry_sleep)
                    continue
                c1 = b""  # the session may already be open — try after anyway
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
                sleep(retry_sleep)  # let the session die before the next init
        raise KWP2000Error(
            f"could not establish {self.name} session after {attempts} attempts: {last}"
        )
