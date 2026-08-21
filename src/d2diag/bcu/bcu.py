"""BCU layer (Valeo body electronics / immobiliser) — **read-only**.

The basis comes from two directions:

* **Address `0x40`, 5-BAUD SLOW INIT — CONFIRMED in the car 2026-08-20.** Handshake
  with KWP2000 keys ``E5 8F`` (as the address hunt 2026-08-05 predicted). Connected
  on the first attempt after an ignition cycle.
* ⚠️ **EKA is LOCKED behind SecurityAccess.** Without ``27 01``/``27 02`` the BCU returns
  a fixed placeholder (``11 99 07 01…``) on BOTH ``1A xx`` and ``21 CC`` — proven
  in the car: all ReadEcuId options + the EKA read gave identical data. The reference tool
  does SecurityAccess IMMEDIATELY after connecting (sniff 2026-08-09), before every read.
  The Valeo seed→key algorithm is **unknown** (unlike the Td5's, which is ported),
  so we can capture a seed but cannot unlock yet. ``identify`` is therefore not reliable
  until unlock exists.
* **The session** from the sniff ``logs/faultread-20260809-2.log``: unaddressed
  length frames, keepalive ``02 3E 01 41`` (with sub-byte, unlike SLABS),
  and ReadDataByLocalIdentifier. **The EKA code is read with `21 CC`** — that frame
  was sent exactly once, right under the operator marker "read set eka".

⚠️ **Read only.** The BCU must never be coded or written blindly: according to the community
a locked BCU cannot be unlocked with diagnostic methods (brick risk). No
key programming, no settings writes, no actuators here.

The BCU enters diagnostic mode on an **ignition transition** — the reference tool asks
the operator to switch off the ignition, press a key, and then switch it on again.
"""
from __future__ import annotations

import time
from typing import Callable

from ..kline.kline import KLineError
from ..kwp2000.kwp2000 import KWP2000Error
from ..session import EcuSession

BCU_ADDRESS = 0x40          # candidate, see module docstring
EKA_LID = 0xCC              # `21 CC` — proven from the sniff 2026-08-09
_DEFAULT_ATTEMPTS = 3


class Bcu(EcuSession):
    """Valeo BCU via 5-baud slow init. Reads EKA code and ECU identification.

    Construct with ``KWP2000(KLine(transport, target=BCU_ADDRESS), tolerant=True)``
    — the session is UNADDRESSED (unlike the airbag).
    """

    name = "BCU"
    # Keepalive with sub-byte: the sniff shows `02 3e 01 41`, not SLABS's bare `3E`.
    _keepalive_sub = 0x01

    def establish(
        self,
        *,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> "tuple[int, int]":
        """5-baud slow init to 0x40. Returns keybytes (KW1, KW2).

        No StartDiagnosticSession and no SecurityAccess — the sniff shows that
        the reference tool does SecurityAccess later in the session, but whether `21 CC` requires
        it we do not know. Try the read first; a ``securityAccessDenied`` (NRC
        0x33) is in itself an answer worth getting.
        """
        last: "Exception | None" = None
        for i in range(attempts):
            if progress:
                progress(f"5-baud slow init to 0x{BCU_ADDRESS:02X} (attempt {i+1}/{attempts})")
            try:
                kw = self._kwp.slow_init(BCU_ADDRESS)
                if progress:
                    progress(f"handshake done, keybytes {kw[0]:02X} {kw[1]:02X}")
                return kw
            except (KLineError, KWP2000Error) as exc:
                last = exc
                if progress:
                    progress(f"no response ({type(exc).__name__})")
                sleep(2.0)  # let the bus go quiet before the next attempt
        raise KWP2000Error(
            f"could not establish BCU session after {attempts} attempts: {last}")

    # ---- identity ------------------------------------------------------ #
    def identify(self, options: "tuple[int, ...]" = (0x80, 0x8A, 0x8B, 0x8D, 0x9B)) -> "dict":
        """Ask the module who it is: ``1A xx`` for a number of options.

        Returns ``{option_hex: bytes}`` for those that answer. If this is the BCU,
        one of the responses should contain readable ASCII (part number/software version) — that
        is how we decide whether the 0x40 guess holds.
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
        """Raw ``21 CC`` — the data field without the echoed LID."""
        return self.read_local(EKA_LID)

    def read_eka(self) -> "dict":
        """Read the EKA code. Returns raw bytes + interpretation candidates.

        The format is **not proven** — the sniff's response to `21 CC` was corrupted (the KKL
        as a passive tap loaded the bus). We only know that the code is **four digits,
        each 1–16** (`references/valeo_bcu_capabilities.md`). So
        the raw bytes are returned plus the two plausible interpretations, so they can be compared
        against a known code instead of guessing:

        * ``bytes`` — one digit per byte (the first four)
        * ``nibbles`` — two digits per byte (high/low nibble)
        """
        raw = self.read_eka_raw()   # NOTE: the tolerant read includes the checksum
        as_bytes = [b for b in raw[:4]]
        nibbles = []
        for b in raw[:2]:
            nibbles += [b >> 4, b & 0x0F]
        return {"raw": raw, "bytes": as_bytes, "nibbles": nibbles,
                "plausible": _plausible(as_bytes, nibbles)}


def find_digits(raw: bytes, digits: "list[int]") -> "dict | None":
    """Search for a KNOWN four-digit code in a raw response and return how it is encoded.

    With the answer in hand the format need not be guessed. We try the encodings that are
    plausible for a code where each digit is 1–16, and search at all offsets — the response
    may have header bytes before the code itself:

    * ``bytes``   — one digit per byte, e.g. ``XX XX XX XX``
    * ``nibbles`` — two digits per byte (BCD-like), e.g. ``79 86``

    Returns ``{"encoding": …, "offset": …}`` or ``None``. The code is passed in
    by the caller; it is never stored in the repo (public) — see ``tools/bcu_probe.py``.
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
    """Which interpretation gives four digits in the valid range 1–16?"""
    ok_b = len(as_bytes) == 4 and all(1 <= d <= 16 for d in as_bytes)
    ok_n = len(nibbles) == 4 and all(1 <= d <= 16 for d in nibbles)
    if ok_b and not ok_n:
        return "bytes"
    if ok_n and not ok_b:
        return "nibbles"
    if ok_b and ok_n:
        return "both (compare against a known code)"
    return "none — the format is something else"
