"""Td5 layer: Td5-specific logic on top of KWP2000.

Diagnostic session, SecurityAccess (seed→key) and reading of identifiers with
scaling to physical values (rpm, temperatures, battery voltage, injector balance …).
The scaling comes from the protocol reference — should be confirmed against the car.
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

# Fault codes: Td5 reads them as a status block via ReadDataByLocalIdentifier 0x3B
# (not standard DTC services) and clears them via StartRoutine 0xDD with 18 zero bytes.
# Derived from the Ekaitza sniff (Read_Faults.log / Read_Faults_and_clear.log).
FAULT_LID = 0x3B
_CLEAR_FAULTS_ROUTINE = 0xDD
_CLEAR_FAULTS_PADDING = b"\x00" * 18

# Output tests — PROVEN from sniff 2026-08-08 (session.log, RDL 016). The reference tool
# pulses TD5 outputs via IOControl `30 <lid> ff`; wastegate/EGR take PWM parameters.
# The injector click is StartRoutine `31 C2 0<n>`. All respond `70/71 <id>` (ack, no data).
_OUTPUTS: "dict[str, tuple[int, bytes]]" = {
    "fuel_pump":   (0xA1, b"\xff"),
    "mil_lamp":    (0xA2, b"\xff"),
    "ac_clutch":   (0xA3, b"\xff"),
    "ac_fan":      (0xA4, b"\xff"),
    "glow_plugs":  (0xB3, b"\xff"),
    "rev_counter": (0xB7, b"\xff"),
    "temp_gauge":  (0xBA, b"\xff"),
    "egr_throttle": (0xBD, b"\xff\x00\xfa\x13\x88"),  # PWM parameters (duty/frequency)
    "wastegate":   (0xBE, b"\xff\x00\x0a\x13\x88"),
}
_INJECTOR_ROUTINE = 0xC2       # `31 C2 0<n>` — pulse injector n (1–5)
_SECURITY_ROUTINE = 0xC0       # `31 C0` start, `33 C0` read status (03 = not immobilised)

# Defaults for establish(): bus idle before init and number of full retries.
_DEFAULT_IDLE = 5.0
_DEFAULT_ATTEMPTS = 6


class Td5(EcuSession):
    name = "Td5"
    _has_session = True  # StartDiagnosticSession 0xA0 → must be closed cleanly on module switch

    # lifecycle (open/close/context) + read_block/tester_present inherited from EcuSession

    def start_session(self) -> bytes:
        """StartDiagnosticSession in the Td5's diagnostic mode (0xA0)."""
        return self._kwp.start_diagnostic_session(TD5_DIAGNOSTIC_SESSION)

    def unlock(self) -> None:
        """SecurityAccess: fetch seed, compute key, send key."""
        seed = self._kwp.request_seed(_SECURITY_LEVEL_SEED)
        if len(seed) < 2:
            raise ValueError(f"unexpected seed length: {seed.hex(' ')}")
        key = key_bytes_from_seed(seed[0], seed[1])
        self._kwp.send_key(key, _SECURITY_LEVEL_KEY)

    def connect(self) -> None:
        """StartDiagnosticSession + SecurityAccess unlock.

        Assumes established communication (fast init already done). After this
        the ECU is unlocked and ``21 xx`` reading works."""
        self.start_session()
        self.unlock()

    def establish(
        self,
        *,
        idle: float = _DEFAULT_IDLE,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> bytes:
        """Full connection: bus idle → tolerant fast init (search for C1) → session →
        unlock (via :meth:`connect`). Retries the whole sequence on noise and
        returns the C1 data field.

        Best against a fresh ECU (ignition cycle just before). ``sleep`` is injected
        for testability. Raises :class:`KWP2000Error` if it fails after
        ``attempts`` attempts. A half-open session responds ``7F`` to
        StartCommunication but can still be unlocked — so an empty C1 is tolerated
        (see :meth:`EcuSession._establish`)."""
        return self._establish(
            after=self.connect, idle=idle, attempts=attempts, retry_sleep=8.0,
            sleep=sleep, progress=progress,
        )

    # ---- reading of live data ---------------------------------------- #
    def read_lid(self, lid: int) -> "dict[str, float]":
        """Read an identifier (21 xx) and decode all signals in it."""
        return decode_lid(lid, self._kwp.read_local_identifier(lid))

    def read(self, name: str) -> float:
        """Read a single signal by name, e.g. 'rpm' or 'coolant_temp'."""
        return self.read_lid(BY_NAME[name].lid)[name]

    def read_all(self) -> "dict[str, float]":
        """Read all known LIDs → {signal_name: value}. A LID that fails is skipped."""
        out: "dict[str, float]" = {}
        for lid in LIDS:
            try:
                out.update(self.read_lid(lid))
            except Exception:  # noqa: BLE001
                pass
        return out

    # ---- fault codes -------------------------------------------------- #
    def read_faults_raw(self) -> bytes:
        """Read the Td5's fault status block (raw bytes after ``61 3B``) via 0x21 0x3B.

        Requires an unlocked session. The block is bit-coded; named decoding is done by
        :func:`d2diag.td5.faults.decode_faults`."""
        return self._kwp.read_local_identifier(FAULT_LID)

    def read_faults(self) -> "list[str]":
        """Read and decode active faults into a list of descriptions."""
        from .faults import decode_faults

        return decode_faults(self.read_faults_raw())

    def clear_faults(self) -> None:
        """Clear stored fault codes (StartRoutine 0xDD). Requires an unlocked session."""
        self._kwp.start_routine(_CLEAR_FAULTS_ROUTINE, _CLEAR_FAULTS_PADDING)

    # ---- output tests (require a TRANSMITTING cable) ------------------ #
    def output_names(self) -> "list[str]":
        """Names of the known output tests (for UI/CLI)."""
        return list(_OUTPUTS)

    def output_test(self, name: str) -> None:
        """Pulse a TD5 output (IOControl). ``name`` from :meth:`output_names`.

        ⚠️ Active test — only run stationary, ignition on. Byte-exact against
        the sniff (e.g. ``ac_clutch`` → ``30 A3 FF``)."""
        try:
            lid, params = _OUTPUTS[name]
        except KeyError:
            raise ValueError(f"unknown TD5 output: {name!r}") from None
        self._kwp.io_control(lid, params)

    def injector_pulse(self, cylinder: int) -> None:
        """Pulse an injector for an audible click (StartRoutine ``31 C2 0<n>``).

        ``cylinder`` 1–5. ⚠️ Active test, engine off."""
        if not 1 <= cylinder <= 5:
            raise ValueError("cylinder must be 1–5")
        self._kwp.start_routine(_INJECTOR_ROUTINE, bytes([cylinder]))

    # ---- immobiliser/security ----------------------------------------- #
    def security_status(self) -> int:
        """Read immobiliser status (`31 C0` start + `33 C0` read). Returns
        the status byte — **0x03 = not immobilised** (proven RDL 016). Read-only.

        (Corresponds to the reference tool's 'GET SECURITY STATUS'. 'LEARN SECURITY CODE' is a
        different, state-changing routine and is deliberately not implemented.)"""
        self._kwp.start_routine(_SECURITY_ROUTINE)
        result = self._kwp.request_routine_results(_SECURITY_ROUTINE)
        # the response starts with the echoed routine id (C0), followed by the status byte
        return result[1] if len(result) >= 2 else -1

    # convenience
    def rpm(self) -> float:
        return self.read("rpm")

    def coolant_temp(self) -> float:
        return self.read("coolant_temp")

    def battery_voltage(self) -> float:
        return self.read("battery")
