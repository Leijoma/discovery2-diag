"""Wabco SLABS (ABS + self-levelling air suspension) module layer.

The protocol is **proven from sniffed reference tool traffic 2026-08-07** (see
``references/slabs_protocol.md`` + raw log ``references/captures/``). Unlike
Td5, **no StartDiagnosticSession and no SecurityAccess** is required — after
fast init you go straight to the services.

  - **Address 0x29**, FAST init: `81 29 F7 81 22` → `C1 57 8F` (KWP2000, KW2=8F).
  - Unaddressed length frames (`02 21 47 …`), keepalive `3E`→`7E`.
  - Fault codes: `21 11` (logged) / `21 47` (current), 16-byte bit-per-fault; clear = `14 FF FF`.
  - Live data: `21 xx`. Actuators/tests: `31 xx` (StartRoutine).

Requires **ignition ON** (ignition-fed). Comms die >8–20 km/h → run stationary.
"""
from __future__ import annotations

import time
from typing import Callable

from ..session import EcuSession
from .faults import FAULT_BLOCK_LEN, decode_fault_block

SLABS_ADDRESS = 0x29

# ReadEcuIdentification options (1A xx)
ECU_ID_CONFIG = 0x8A
ECU_ID_VERSIONS = 0x8B
ECU_ID_VIN = 0x8D

# Fault memory
LOGGED_FAULTS_LID = 0x11   # 21 11
CURRENT_FAULTS_LID = 0x47  # 21 47
CLEAR_FAULTS_SERVICE = 0x14  # 14 FF FF → 54

# StartRoutine identifiers (31 xx), proven from the sniff
RID_PUMP_RELAY = 0x25
RID_EXHAUST_VALVE = 0x2F
RID_COMPRESSOR = 0x30
RID_BUZZER = 0x31
RID_RAISE_LEFT = 0x33
RID_RAISE_RIGHT = 0x34
RID_LOWER_LEFT = 0x35
RID_LOWER_RIGHT = 0x36
RID_ABS_TEST = 0x22  # bleed + wheel tests; sub-byte selects circuit

# ABS_TEST subcommands (byte after 0x22)
ABS_SUB_POWER_BLEED = 0x04
ABS_SUB_FRONT_RIGHT = 0x10
ABS_SUB_FRONT_LEFT = 0x11
ABS_SUB_REAR_RIGHT = 0x12
ABS_SUB_REAR_LEFT = 0x13

_DEFAULT_IDLE = 0.3    # proven stable value (sniff 2026-08-07)
# MEASURED from the reference tool sniffs (2026-08-07/08/09, see slabs_protocol.md): EVERY
# successful SLABS init came on the first attempt after 25–28 s with no traffic to the module —
# 24.9, 26.5, 27.8, 28.0, 41.0, 51.5 s. The tool NEVER made a fast retry.
# The module thus needs a quiet period to release its link, and every init we
# send during it resets the wait. Hammering is therefore actively harmful: it is
# what kept us locked out for ~2 min 2026-08-18.
_DEFAULT_ATTEMPTS = 3
_DEFAULT_RETRY_SLEEP = 28.0
_CONFIRM_DELAY = 0.15  # pause between C1 and 1A 8A (reference tool: ~170 ms in the sniff)


class Slabs(EcuSession):
    """Wabco SLABS via fast init 0x29. Read + clear + actuators.

    Lifecycle (open/close/context), :meth:`read_block` and :meth:`tester_present`
    are inherited from :class:`EcuSession`."""

    name = "SLABS"
    _keepalive_sub = None  # SLABS wants a bare 3E (sniffed frame 01 3e 3f), not 3E 01

    # Cycle address mode between attempts. Functional first because those frames accounted
    # for 6 hits out of 24 versus physical 1 out of 21 in the car 2026-08-19 — BUT that number is
    # conflated with the attempt number: the probe always ran the variants in the same
    # order, and physical/F7 always came first. It may therefore just as well be that
    # the first attempt wakes the module and the next one gets through. The order here is thus
    # a guess that costs nothing; what matters is that SEVERAL attempts are made.
    _init_variants = ((True, 0xF1), (True, 0xF7), (False, None))

    def establish(
        self,
        *,
        idle: float = _DEFAULT_IDLE,
        attempts: int = _DEFAULT_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        progress: "Callable[[str], None] | None" = None,
    ) -> bytes:
        """Bus idle → tolerant fast init to 0x29 (search for C1) → acknowledgement with `1A 8A`.

        Returns the C1 data field (`57 8F`). No session/unlock needed
        (``after=None``). Raises :class:`KWP2000Error` after ``attempts`` attempts.

        **`1A 8A` as the first request mirrors the reference tool.** In every successful init
        in the sniffs, the tool's first message after `C1` is a
        `02 1a 8a a6` → `5a 8a …`, ~170 ms later, before keepalive and reads
        begin. We do the same and use the response as **acknowledgement that the session
        really is alive** — our tolerant init only looks for a `C1` in the burst
        and in noise can give a false positive "session established" followed by zero
        reads (seen in the car 2026-08-18). A failed acknowledgement does NOT tear down
        the establishment; it is reported via ``progress`` so the connection log shows
        the difference between "up" and "thought we were up".
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
        """Send `1A 8A` as the reference tool does and report the outcome. Best-effort."""
        sleep(_CONFIRM_DELAY)  # the tool waits ~170 ms after C1 before 1A 8A
        try:
            ident = self.read_ecu_id(ECU_ID_CONFIG)
        except Exception as exc:  # noqa: BLE001 — the acknowledgement must not tear down the establishment
            if progress:
                progress(f"no answer to 1A 8A ({type(exc).__name__}) — session may be dead")
            return False
        if progress:
            progress(f"session confirmed (1A 8A → {ident[:6].hex(' ')}…)")
        return True

    # ---- ECU identity (1A xx) ---------------------------------------- #
    def read_ecu_id(self, option: int) -> bytes:
        """ReadEcuIdentification. Returns the data field (without the echoed option byte)."""
        return self._kwp.request(0x1A, bytes([option]))[1:]

    def read_vin(self) -> str:
        return self.read_ecu_id(ECU_ID_VIN).split(b"\x00", 1)[0].decode("ascii", "replace").strip()

    def read_software_versions(self) -> "list[str]":
        raw = self.read_ecu_id(ECU_ID_VERSIONS)
        return [p.decode("ascii", "replace") for p in raw.split(b"\x00") if p]

    # ---- fault codes -------------------------------------------------- #
    def _fault_block(self, lid: int) -> bytes:
        return self._kwp.read_local_identifier(lid)[:FAULT_BLOCK_LEN]

    def read_logged_faults_raw(self) -> bytes:
        return self._fault_block(LOGGED_FAULTS_LID)

    def read_current_faults_raw(self) -> bytes:
        return self._fault_block(CURRENT_FAULTS_LID)

    def read_faults(self) -> "dict[str, list[str]]":
        """Decoded fault codes: {"loggade": [...], "aktuella": [...]}."""
        return {
            "loggade": decode_fault_block(self.read_logged_faults_raw()),
            "aktuella": decode_fault_block(self.read_current_faults_raw()),
        }

    def clear_faults(self) -> None:
        """ClearDiagnosticInformation (14 FF FF) → 54. Clears the fault memory.

        ⚠️ The ack is DELAYED: SLABS writes to EEPROM and only responds `54`
        ~300 ms after the command (proven from sniff session.log: TX @72560,
        RX @72856). The standard read's 60 ms gap then returns only the echo and we
        threw "empty response" even though the clear succeeded. So read with a wider
        window (gap 0.5 s, overall 2.5 s) so we catch `54`.
        """
        self._kwp.request(CLEAR_FAULTS_SERVICE, b"\xff\xff", overall=2.5, gap=0.5)

    # ---- live data (21 xx) ------------------------------------------- #
    def read_data(self, lid: int) -> bytes:
        """Raw ReadDataByLocalIdentifier (21 xx). Data field without the echoed LID."""
        return self._kwp.read_local_identifier(lid)

    # ---- actuators / tests (31 xx) ----------------------------------- #
    # ⚠️ All of these TOUCH HARDWARE. Run stationary, ignition on.
    def start_routine(self, rid: int, params: bytes = b"") -> bytes:
        """Generic StartRoutine (31 xx). Returns the response (starts with the echoed RID)."""
        return self._kwp.start_routine(rid, params)

    def buzzer(self) -> None:
        """⚠️ SLS buzzer on (harmless, audible — good write verification)."""
        self.start_routine(RID_BUZZER, b"\x0a")

    def compressor(self) -> None:
        """⚠️ SLS compressor."""
        self.start_routine(RID_COMPRESSOR, b"\x28")

    def exhaust_valve(self) -> None:
        """⚠️ SLS exhaust valve."""
        self.start_routine(RID_EXHAUST_VALVE, b"\x28")

    def pump_relay(self, on: bool = True) -> None:
        """⚠️ ABS pump relay. Param `08 fa`/`02 fa` proven from sniff (on/off preliminary;
        trailing byte in the log = checksum, not param)."""
        self.start_routine(RID_PUMP_RELAY, b"\x08\xfa" if on else b"\x02\xfa")

    def raise_corner(self, side: str) -> None:
        """⚠️ Raise air suspension. side ∈ {'left','right'}."""
        self.start_routine(RID_RAISE_LEFT if side == "left" else RID_RAISE_RIGHT, b"\x28")

    def lower_corner(self, side: str) -> None:
        """⚠️ Lower air suspension. side ∈ {'left','right'}."""
        self.start_routine(RID_LOWER_LEFT if side == "left" else RID_LOWER_RIGHT, b"\x28")

    # Wheel → (sub, valve mask). Proven from sniff: 2 bits/wheel in order FR,FL,RR,RL.
    _WHEEL = {
        "fr": (0x10, 0x03), "fl": (0x11, 0x0c),
        "rr": (0x12, 0x30), "rl": (0x13, 0xc0),
    }

    def wheel_test(self, corner: str) -> None:
        """⚠️ ABS valve test on ONE wheel. corner ∈ {'fl','fr','rl','rr'}.
        `31 22 <sub> <mask> c1 f4` + 8 zero bytes (proven from sniff)."""
        sub, mask = self._WHEEL[corner]
        self.start_routine(RID_ABS_TEST, bytes([sub, mask, 0xc1, 0xf4]) + bytes(8))

    # ---- ABS bleed (proven from sniff 2026-08-07) -------------------------- #
    # Two procedures under RID_ABS_TEST (0x22), distinct from the wheel valve test above:
    #   * POWER BLEED — runs the ABS pump so fluid is forced through the modulator.
    #       start `31 22 04 00 49 c4 …`, stop `31 22 04 00 40 00 …`
    #   * MODULE BLEED — cycles the modulator's circuits 0x11→0x14 in sequence,
    #       each step `31 22 <sub> 00 c0 7d 00 bb …` (~2.3 s between in the sniff).
    def abs_power_bleed(self, on: bool = True) -> None:
        """⚠️ ABS POWER BLEED — runs the pump to force brake fluid through the
        modulator. ``on`` starts (`04 00 49 c4`), ``on=False`` stops
        (`04 00 40 00`). Brake system — stationary only, see safety notes."""
        tail = b"\x00\x49\xc4" if on else b"\x00\x40\x00"
        self.start_routine(RID_ABS_TEST, bytes([0x04]) + tail + bytes(8))

    _BLEED_STEPS = (0x11, 0x12, 0x13, 0x14)  # modulator circuits in the sniff's order

    def abs_module_bleed_step(self, step: int) -> None:
        """⚠️ One step in MODULE BLEED (``step`` 1–4 → sub 0x11–0x14).
        `31 22 <sub> 00 c0 7d 00 bb` + 6 zero bytes. Brake system — stationary."""
        if not 1 <= step <= 4:
            raise ValueError("step must be 1–4")
        sub = self._BLEED_STEPS[step - 1]
        self.start_routine(RID_ABS_TEST, bytes([sub, 0x00, 0xc0, 0x7d, 0x00, 0xbb]) + bytes(6))

    def abs_module_bleed(self, sleep: "Callable[[float], None] | None" = None,
                         gap: float = 2.3) -> None:
        """⚠️ The whole MODULE BLEED sequence: four steps 0x11→0x14 with ``gap`` s between
        (the reference tool's cadence in the sniff). Brake system — stationary, ignition on."""
        _sleep = sleep or time.sleep
        for step in range(1, 5):
            self.abs_module_bleed_step(step)
            if step < 4:
                _sleep(gap)
