"""Airbag (TRW SPS 2A, SRS) module layer — **READ-ONLY, EXPERIMENTAL**.

🔴 Pyrotechnic safety module. This layer **only reads** fault codes (`21 02`).
No clear, no outputs, no SecurityAccess — deliberately not implemented.

Protocol (derived from ONE sniffed sequence, `faultread-20260809.log` line 1121–1122,
RDL 016 2026-08-10) — differs from Td5/SLABS:
  - **Address 0x5B, 5-baud SLOW init** (`55` sync), then **ADDRESSED framing per
    message** (`82 5b f7 …`), not unaddressed session frames.
  - **StartDiagnosticSession `10 81`** → `50 81` (session 0x81, not the Td5's 0xA0).
  - Fault memory: **`21 02`** → `61 02` + records `[status][fault-number]` (decoded by
    :func:`decode_faults`). `21 01` was seen empty.

⚠️ **Unverified against the car by us.** The reference tool did SecurityAccess (seed→key) BEFORE
the read; we cannot reproduce it (only one captured pair, no algorithm).
If `21 02` REQUIRES an unlocked session this fails with a negative response — then airbag
reading is blocked until the algorithm is known. Reading is harmless; if it fails
softly that is acceptable.
"""
from __future__ import annotations

import time
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000Error
from ..session import EcuSession
from .faults import FAULT_LID, decode_faults

AIRBAG_ADDRESS = 0x5B
_SESSION = 0x81            # StartDiagnosticSession subfunction (10 81 → 50 81)
_DEFAULT_ATTEMPTS = 3


class Airbag(EcuSession):
    """TRW SPS 2A via slow init 0x5B + addressed framing. **Read only.**

    Construct with ``KWP2000(KLine(transport, target=0x5B), tolerant=True,
    addressed=True)``. Lifecycle/`read_local`/`read_block` inherited from EcuSession.
    """

    name = "Airbag"

    def establish(
        self,
        *,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "tuple[int, int]":
        """5-baud slow init to 0x5B → StartDiagnosticSession (10 81). Returns
        keybytes (KW1, KW2). No SecurityAccess. Raises :class:`KWP2000Error`
        after ``attempts`` attempts."""
        last: "Exception | None" = None
        for _ in range(attempts):
            try:
                kw = self._kwp.slow_init(AIRBAG_ADDRESS)
                self._kwp.start_diagnostic_session(_SESSION)
                return kw
            except (KLineError, KWP2000Error) as exc:
                last = exc
                sleep(2.0)  # let the bus go quiet before the next slow-init attempt
        raise KWP2000Error(f"could not establish Airbag session after {attempts} attempts: {last}")

    # ---- fault codes (the ONLY write-free operation) ------------------- #
    def read_faults_raw(self) -> bytes:
        """Raw fault memory (data field after ``61 02``) via `21 02`."""
        return self._kwp.read_local_identifier(FAULT_LID)

    def read_faults(self) -> "list[dict]":
        """Decoded SRS faults → ``[{number, status, status_text}]`` (see
        :func:`d2diag.airbag.faults.decode_faults`)."""
        return decode_faults(self.read_faults_raw())
