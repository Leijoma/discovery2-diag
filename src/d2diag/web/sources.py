"""Data sources for the dashboard.

A ``DataSource`` supplies a snapshot (``poll()``) with status, signals
(name → value/unit) and fault codes. ``MockDataSource`` simulates a car for
UI development without hardware. ``Td5DataSource`` reads the real Td5 ECU.
"""
from __future__ import annotations

import abc
import datetime as _dt
import glob
import json
import math
import os
import random
import time

from ..signals import load_signals
from ..td5.identifiers import BY_NAME, signal_status


def _raw_log_path(module: str, raw_log_dir: "str | None") -> "str | None":
    """Path for a raw TX/RX log, or None if raw logging is off.

    One file per module and dashboard start (``raw-<module>-<time>.log``).
    LoggingTransport opens in append mode, so reconnects (module switch,
    error retry) continue in the SAME file — an unbroken bus log for mapping."""
    if not raw_log_dir:
        return None
    os.makedirs(raw_log_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(raw_log_dir, f"raw-{module}-{stamp}.log")


def _transport(port: str, raw_log_path: "str | None"):
    """SerialTransport, optionally wrapped in LoggingTransport for a raw TX/RX log.

    Lazy import so the Mock sources can run without pyserial. When raw logging is on,
    LoggingTransport sits transparently under KLine and captures every byte both ways."""
    from ..transport import SerialTransport
    inner = SerialTransport(port, timeout=1.0)
    if raw_log_path:
        from ..transport import LoggingTransport
        return LoggingTransport(inner, logfile=raw_log_path)
    return inner


# Full reference tool coverage: also read LIDs the reference tool polls but we haven't mapped yet, so
# the raw log captures ALL available data — then unmapped fields can be found from a normal
# drive (that's how MAF was found in 1D 2026-08-21). "Don't throw away the bytes we haven't named."
#
# TD5 (not session-sensitive): read the extra LIDs EVERY cycle so they're sampled alongside rpm.
# 1E/1F/20 = confirmed responding in the fuelling block (lid_sweep 2026-08-21); 1E carries
# switch/digital-in bits (byte0 bit0 = brake, car test 2026-08-21). 36 = the second
# switch block (Ekaitza) — added to catch A/C/handbrake bits. (37/38
# from SimonRafferty do NOT respond on RDL016, removed.)
_TD5_COVERAGE_EXTRA = (0x1E, 0x1F, 0x20, 0x36)
# SLABS (MUST be polled lightly — block reading kills the session): these LIDs are rotated
# ONE per cycle (the 0x54 heights are read every cycle anyway). Source: slabs/menu.py +
# references/reference_tool_menu_map.md (the reference tool menu's input block).
_SLABS_COVERAGE = frozenset({
    0x11, 0x3B, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x50, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
})

# Fuel computer: fields derived from injection quantity + rpm + speed. Not a LID read →
# unit + confidence are given here (injection_qty is a candidate, so consumption is too).
_INJ_PER_REV = 2.5          # 5-cyl 4-stroke: 5/2 injections per crankshaft revolution
_DIESEL_G_PER_L = 832.0     # diesel density
_DERIVED_TD5 = {
    "fuel_rate":        ("L/h", "kandidat"),
    "economy":          ("L/100km", "kandidat"),
    "trip_economy":     ("L/100km", "kandidat"),
    "lifetime_economy": ("L/100km", "kandidat"),
}


class _FuelComputer:
    """Instantaneous consumption + trip and lifetime averages from injection quantity
    (mg/stroke), rpm and speed. Integrates with REAL time between polls (time.monotonic).

    L/h = inj[mg/stroke] × injections/rev × rpm × 60 / 1e6 / (density g/ml).
    Trip = since the object was created (dashboard start). Lifetime = persisted to file.
    """

    def __init__(self, state_path: "str | None" = None,
                 clock: "callable" = time.monotonic) -> None:
        self._state_path = state_path
        self._clock = clock
        self._last: "float | None" = None
        self._trip_fuel = 0.0   # L
        self._trip_dist = 0.0   # km
        self._life_fuel, self._life_dist = self._load()
        self._tick = 0

    def _load(self) -> "tuple[float, float]":
        if self._state_path and os.path.exists(self._state_path):
            try:
                d = json.load(open(self._state_path, encoding="utf-8"))
                return float(d.get("fuel_l", 0.0)), float(d.get("dist_km", 0.0))
            except (OSError, ValueError, TypeError):
                pass
        return 0.0, 0.0

    def _save(self) -> None:
        if not self._state_path:
            return
        try:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"fuel_l": round(self._life_fuel, 4),
                           "dist_km": round(self._life_dist, 3)}, fh)
            os.replace(tmp, self._state_path)
        except OSError:
            pass

    def pause(self) -> None:
        """Zero the clock (on module switch/reconnect) so a gap isn't integrated."""
        self._last = None

    def update(self, inj_mg: "float | None", rpm: "float | None",
               speed_kmh: "float | None") -> "dict":
        now = self._clock()
        rate = None
        if inj_mg is not None and rpm:
            rate = inj_mg * _INJ_PER_REV * rpm * 60.0 / 1e6 / (_DIESEL_G_PER_L / 1000.0)
        if self._last is not None and rate is not None:
            dt_h = min(now - self._last, 3.0) / 3600.0   # cap 3 s → no spike after a pause
            self._trip_fuel += rate * dt_h
            self._life_fuel += rate * dt_h
            if speed_kmh:
                d = speed_kmh * dt_h
                self._trip_dist += d
                self._life_dist += d
        self._last = now

        out: "dict[str, float]" = {}
        if rate is not None:
            out["fuel_rate"] = round(rate, 2)
            if speed_kmh and speed_kmh > 5:                 # economy only when moving
                out["economy"] = round(rate / speed_kmh * 100.0, 1)
        if self._trip_dist > 0.1:
            out["trip_economy"] = round(self._trip_fuel / self._trip_dist * 100.0, 1)
        if self._life_dist > 1.0:
            out["lifetime_economy"] = round(self._life_fuel / self._life_dist * 100.0, 1)
        self._tick += 1
        if self._tick % 60 == 0:                            # persist lifetime ~every 30-60 s
            self._save()
        return out

# Chip hints for recognising a KKL/OBD cable among several USB serial devices.
_KKL_HINTS = ("ft232", "ftdi", "ch340", "cp210", "usb-serial", "usb_uart", "obd", "kkl")


# macOS call-out ports (use cu.*, NEVER tty.* — tty blocks on DCD).
_MAC_GLOBS = (
    "/dev/cu.usbserial-*", "/dev/cu.usbmodem*",
    "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*",
)


def resolve_serial_port(spec: "str | None") -> str:
    """Return a concrete serial port.

    A ``spec`` that is a real path is returned unchanged. ``None`` or
    ``"auto"`` auto-detects a USB serial device. Order: **stable**
    ``/dev/serial/by-id/`` links (Linux) → ``/dev/cu.*`` (macOS) → ``ttyUSB*`` /
    ``ttyACM*``. Within by-id and cu.*, a known KKL chip (``_KKL_HINTS``) is preferred.
    Raises :class:`FileNotFoundError` if none is found (e.g. the cable not plugged in
    yet) — called again on every connection attempt.
    """
    if spec and spec != "auto":
        return spec
    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    mac = sorted(p for pat in _MAC_GLOBS for p in glob.glob(pat))
    preferred_id = [p for p in by_id if any(h in p.lower() for h in _KKL_HINTS)]
    preferred_mac = [p for p in mac if any(h in p.lower() for h in _KKL_HINTS)]
    for candidates in (preferred_id, by_id, preferred_mac, mac,
                       sorted(glob.glob("/dev/ttyUSB*")),
                       sorted(glob.glob("/dev/ttyACM*"))):
        if candidates:
            return candidates[0]
    raise FileNotFoundError("no USB serial device found (KKL not connected?)")

# Unit map from the identifier table (name → unit).
UNITS = {name: sig.unit for name, sig in BY_NAME.items()}


def _conf_map(module: str) -> "dict[str, str]":
    """{signal name → confidence} from the signal store (proven/candidate)."""
    return {s.name: s.confidence for s in load_signals(module)}


def _conf_of(module: str, name: str, conf: "dict[str, str]") -> str:
    """Confidence for a signal — from the store, otherwise a heuristic for derived fields.
    The trust view (Verified/Explorer) filters on this."""
    if name in conf:
        return conf[name]
    if module == "slabs":
        if name.startswith("height_"):
            return "belagt"          # derived from a proven height
        if name.startswith(("wheel_speed_", "abs_sensor_")):
            return "kandidat"        # wheel speed/voltage: scale not confirmed
    return "belagt"


def _sig(values: "dict[str, float]", module: str = "td5") -> "dict[str, dict]":
    """Package {name: value} → {name: {"v", "u", "s", "c"}} (c = confidence)."""
    conf = _conf_map(module)
    out = {}
    for k, v in values.items():
        vr = round(v, 2)
        if k in _DERIVED_TD5:                # computed fields (fuel computer)
            unit, c = _DERIVED_TD5[k]
        else:
            unit, c = UNITS.get(k, ""), _conf_of(module, k, conf)
        out[k] = {"v": vr, "u": unit, "s": signal_status(k, vr), "c": c}
    return out


def _sleep_kw(hook) -> "dict":
    """``{"sleep": hook}`` if a hook exists, otherwise empty (keep time.sleep)."""
    return {} if hook is None else {"sleep": hook}


class DataSource(abc.ABC):
    """Contract: ``poll()`` returns a fresh snapshot dict."""

    name: str = "source"
    on_progress = None  # callback(str): live status during blocking establishment (base: none)
    # sleep hook for the establishment's wait times (the SLABS quiet period is 28 s). The server
    # sets an interruptible variant so a module switch doesn't have to wait it out.
    on_sleep = None

    def is_connected(self) -> bool:
        """Does the source have a live session? Base: no (mock always reports connected via poll)."""
        return False

    @abc.abstractmethod
    def poll(self) -> "dict":
        """Return {status, signals, faults, error?}."""

    def disconnect(self) -> None:
        """Release any K-line session/port (on module switch). Base: nothing to do."""

    def menu_map(self) -> "list":
        """Reference/coverage map (reference tool menu + our status). Base: empty."""
        return []

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        """Perform a write command. Base: unknown. Returns {ok, message|error}.

        Runs on the poller thread (serialized with poll) so K-line access never
        collides. Writes to the ECU are sensitive — only explicitly supported
        actions are allowed; risky ones (actuator tests, settings) aren't exposed here.
        """
        return {"ok": False, "error": f"unknown command: {action}"}


class MockDataSource(DataSource):
    """Simulated car for UI dev: reasonable, moving values + one active fault."""

    name = "mock"

    _ACTIVE_FAULT = "inlet air temp. circuit (Current)"
    _LOGGED_FAULT = "air flow circuit (Logged Low)"

    def __init__(self) -> None:
        self._t = 0.0
        self._coolant = 20.0  # cold start, warming up
        self._faults = [self._LOGGED_FAULT, self._ACTIVE_FAULT]
        self._cleared_ticks = 0  # >0 = just cleared, faults temporarily gone

    def poll(self) -> "dict":
        self._t += 1
        # idle with a little variation, and a "throttle blip" pulse now and then
        revving = (int(self._t) % 30) in (10, 11, 12, 13)
        base = 2200 if revving else 800
        rpm = base + random.uniform(-40, 60)
        speed = max(0.0, (rpm - 800) / 45) if revving else 0.0
        self._coolant = min(88.0, self._coolant + 0.15)  # creeps towards working temp
        manifold = 1.0 + (0.25 if revving else 0.0) + random.uniform(-0.01, 0.01)
        signals = {
            "rpm": rpm,
            "speed": speed,
            "battery": 14.1 + random.uniform(-0.15, 0.15),
            "coolant_temp": self._coolant,
            "air_temp": 120.0,  # locked → mirrors the IAT fault on the real car
            "fuel_temp": self._coolant - 6 + random.uniform(-1, 1),
            "manifold_press": manifold,
            "ambient_press_1": 1.01,
            # Fuel economy (L/100km) so the Drive tab preview shows L/mil; live values
            # come from the real fuel computer in Td5DataSource.
            "economy": 8.2 + random.uniform(-0.4, 0.4),
            "trip_economy": 7.9 + random.uniform(-0.1, 0.1),
            "rpm_error": random.uniform(-8, 8),
            "balance_1": random.uniform(-4, 4),
            "balance_2": random.uniform(-4, 4),
            "balance_3": random.uniform(-4, 4),
            "balance_4": random.uniform(-4, 4),
            "balance_5": random.uniform(-4, 4),
        }
        # After clearing, the list is empty for a few polls, then the ACTIVE
        # fault returns (still faulty) — demonstrates "clear and see if it comes back".
        if self._cleared_ticks > 0:
            self._cleared_ticks -= 1
            if self._cleared_ticks == 0:
                self._faults = [self._ACTIVE_FAULT]
        return {
            "status": "connected",
            "source": self.name,
            "signals": _sig(signals),
            "faults": list(self._faults),
        }

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        if action == "clear_faults":
            self._faults = []
            self._cleared_ticks = 4  # empty for ~4 polls, then the active fault returns
            return {"ok": True, "message": "Fault codes cleared (mock)"}
        return {"ok": False, "error": f"unknown command: {action}"}

    def menu_map(self) -> "list":
        from ..td5.menu import TD5_MENU
        return TD5_MENU


def _read_block_cmd(session, params: "dict | None") -> "dict":
    """Read a set of LIDs via a live session → {ok, raws:{lidhex:hex}}.

    The read-only primitive behind the active differential mapping in the Map tab
    (baseline/read-again). Shared by the Td5 and SLABS sources."""
    if session is None:
        return {"ok": False, "error": "not connected"}
    lids_in = (params or {}).get("lids") or []
    try:
        lids = [int(x, 16) if isinstance(x, str) else int(x) for x in lids_in]
    except (ValueError, TypeError):
        return {"ok": False, "error": "ogiltiga lids"}
    try:
        raws = session.read_block(lids)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "raws": {k: v.hex() for k, v in raws.items()}}


class Td5DataSource(DataSource):
    """Real Td5 ECU. Establishes the session lazily and re-reads on error.

    Requires hardware; imports heavy dependencies locally so Mock can run standalone.
    """

    name = "td5"

    def __init__(self, port: str, read_faults: bool = True,
                 raw_log_dir: "str | None" = None,
                 fuel_state_path: "str | None" = None) -> None:
        self._port = port
        self._read_faults = read_faults
        self._raw_log_path = _raw_log_path("td5", raw_log_dir)
        self._fuel = _FuelComputer(fuel_state_path)  # fuel computer (instantaneous/trip/lifetime)
        self._td5 = None
        self._faults: "list[str]" = []
        self._fault_tick = 0
        self.fault_every = 10  # read fault codes every Nth poll (1 = "fault watch", every cycle)
        self.on_progress = None  # callback(str): live status during blocking establishment

    def is_connected(self) -> bool:
        return self._td5 is not None

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..td5 import Td5

        if self.on_progress:
            self.on_progress("opening the cable")
        port = resolve_serial_port(self._port)  # auto-detect on every attempt
        td5 = Td5(KWP2000(KLine(_transport(port, self._raw_log_path)), tolerant=True))
        td5.open()
        td5.establish(progress=self.on_progress, **_sleep_kw(self.on_sleep))
        return td5

    def disconnect(self) -> None:
        # release() = StopDiagnosticSession + close. Just close() leaves the TD5 session
        # open on the shared bus → the next module (SLABS) gets 7F 81 10 on its init.
        try:
            if self._td5 is not None:
                self._td5.release()
        except Exception:  # noqa: BLE001
            pass
        self._td5 = None
        self._fuel.pause()  # zero the fuel computer's clock so the reconnect gap isn't counted

    def menu_map(self) -> "list":
        from ..td5.menu import TD5_MENU
        return TD5_MENU

    def poll(self) -> "dict":
        try:
            if self._td5 is None:
                self._td5 = self._connect()
            signals = self._td5.read_all()
            if not signals:
                # the session is "up" but all reads failed (noise/dropped cable) →
                # treat as lost contact so we reconnect on the next poll.
                raise RuntimeError("no signals read — noise or lost connection")
            # Full coverage: read the unmapped LIDs the reference tool polls → they land in the raw log
            # (not decoded, but captured for future mapping). An error here must not
            # fell the poll — read_all already succeeded.
            try:
                self._td5.read_block(_TD5_COVERAGE_EXTRA)
            except Exception:  # noqa: BLE001
                pass
            # Fuel computer: instantaneous L/h + L/100km, trip and lifetime averages, from
            # injection quantity + rpm + speed. Derived fields, integrated over time.
            signals.update(self._fuel.update(
                signals.get("injection_qty"), signals.get("rpm"), signals.get("speed")))
            # read fault codes less often (expensive); every ~10th poll
            if self._read_faults and self._fault_tick % self.fault_every == 0:
                try:
                    self._faults = [f for f in self._td5.read_faults() if not f.startswith("byte")]
                except Exception:  # noqa: BLE001
                    pass
            self._fault_tick += 1
            return {
                "status": "connected",
                "source": self.name,
                "signals": _sig(signals),
                "faults": self._faults,
            }
        except Exception as exc:  # noqa: BLE001 — drop the session and reconnect next poll
            try:
                if self._td5 is not None:
                    self._td5.release()  # tear down the link (82) — otherwise 7F 81 10 on reconnect
            except Exception:  # noqa: BLE001
                pass
            self._td5 = None
            return {"status": "error", "source": self.name, "signals": {}, "faults": [],
                    "error": f"{type(exc).__name__}: {exc}"}

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        if action == "read_block":
            return _read_block_cmd(self._td5, params)
        if action == "clear_faults":
            if self._td5 is None:
                return {"ok": False, "error": "not connected to the ECU"}
            try:
                self._td5.clear_faults()
                self._fault_tick = 0  # force a re-read of fault codes next poll
                return {"ok": True, "message": "Fault codes cleared"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        # Output tests (IOControl) + injector pulse. Proven from sniff 2026-08-08 but
        # NEVER run from our code against the car → experimental until verified.
        # Hardware writes: the UI gates them behind a confirmation.
        if self._td5 is None:
            return {"ok": False, "error": "not connected to the ECU"}
        try:
            if action.startswith("output_"):
                name = action[len("output_"):]
                self._td5.output_test(name)
                return {"ok": True, "message": f"Output test: {name}"}
            if action.startswith("injector_"):
                cyl = int(action[len("injector_"):])
                self._td5.injector_pulse(cyl)
                return {"ok": True, "message": f"Injector {cyl} pulse"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": False, "error": f"unknown command: {action}"}


# --- SLABS (Wabco ABS/SLS) ------------------------------------------------ #
_SLABS_UNITS = {"height_left_mm": "mm", "height_right_mm": "mm"}


def _slabs_sig(values: "dict[str, float]") -> "dict[str, dict]":
    conf = _conf_map("slabs")
    return {k: {"v": round(v, 1), "u": _SLABS_UNITS.get(k, ""), "s": None,
                "c": _conf_of("slabs", k, conf)}
            for k, v in values.items()}


def _slabs_decode_store(raws: "dict[int, bytes]") -> "dict[str, float]":
    """Decode all SLABS store fields we have raw bytes for → {name: value}.

    Store-driven, so a new confirmed mapping in ``slabs.json`` shows up in the UI
    without a code change. The heights are supplemented with derived mm fields (the SVG
    car). Fields with a state label (any_door) are NOT included here — they go as numeric
    0/1 and the label is set in the UI layer if needed.
    """
    vals: "dict[str, float]" = {}
    for sig in load_signals("slabs"):
        raw = raws.get(sig.lid)
        if raw is not None and sig.fits(raw):
            vals[sig.name] = round(sig.decode(raw), 3)
    if "height_left" in vals:
        vals["height_left_mm"] = round(vals["height_left"] * 1.4, 1)
    if "height_right" in vals:
        vals["height_right_mm"] = round(vals["height_right"] * 1.4, 1)
    return vals


def _slabs_faults_flat(f: "dict[str, list]") -> "list[str]":
    """{"loggade":[…],"aktuella":[…]} → flat list with (Logged)/(Current) tags."""
    return [x + " (Logged)" for x in f.get("loggade", [])] + \
           [x + " (Current)" for x in f.get("aktuella", [])]


# Actuator actions (web → SLABS). Name → Swedish label (for mock responses/UI).
_SLABS_ACTUATORS = {
    "buzzer": "Buzzer test", "compressor": "Compressor test", "exhaust": "Exhaust valve test",
    "pump_on": "ABS pump on", "pump_off": "ABS pump off",
    "raise_left": "Raise left", "raise_right": "Raise right",
    "lower_left": "Lower left", "lower_right": "Lower right",
    "wheel_fl": "Valve test FL", "wheel_fr": "Valve test FR",
    "wheel_rl": "Valve test RL", "wheel_rr": "Valve test RR",
    "bleed_power_on": "ABS power bleed — start", "bleed_power_off": "ABS power bleed — stop",
    "bleed_module": "ABS module bleed (4-step sequence)",
}


def _slabs_do(slabs, action: str) -> None:
    """Run an actuator action against a real Slabs object."""
    if action == "buzzer":
        slabs.buzzer()
    elif action == "compressor":
        slabs.compressor()
    elif action == "exhaust":
        slabs.exhaust_valve()
    elif action == "pump_on":
        slabs.pump_relay(True)
    elif action == "pump_off":
        slabs.pump_relay(False)
    elif action.startswith("raise_"):
        slabs.raise_corner(action.split("_", 1)[1])
    elif action.startswith("lower_"):
        slabs.lower_corner(action.split("_", 1)[1])
    elif action.startswith("wheel_"):
        slabs.wheel_test(action.split("_", 1)[1])
    elif action == "bleed_power_on":
        slabs.abs_power_bleed(True)
    elif action == "bleed_power_off":
        slabs.abs_power_bleed(False)
    elif action == "bleed_module":
        slabs.abs_module_bleed()
    else:
        raise ValueError(f"unknown command: {action}")


class MockSlabsDataSource(DataSource):
    """Simulated SLABS for UI dev: moving heights + the baseline's two logged faults."""

    name = "slabs"

    def __init__(self) -> None:
        self._t = 0.0
        self._faults = {
            "loggade": [
                "020: front right wheel speed sensor — output too low",
                "027: shuttle valve switch — electrical failure",
            ],
            "aktuella": [],
        }
        self._cleared = 0

    def poll(self) -> "dict":
        self._t += 1
        hl = 143 + 2 * math.sin(self._t / 10)
        hr = 157 + 2 * math.cos(self._t / 12)
        vals = {
            "height_left": hl, "height_right": hr,
            "height_left_mm": hl * 1.4, "height_right_mm": hr * 1.4,
        }
        for w in ("fl", "fr", "rl", "rr"):  # wheel: speed (~124 raw value at rest) + sensor voltage
            vals[f"wheel_speed_{w}"] = 124.0
            vals[f"abs_sensor_{w}"] = round(2.3 + random.uniform(-0.05, 0.05), 2)
        signals = _slabs_sig(vals)
        if self._cleared > 0:
            self._cleared -= 1
            if self._cleared == 0:
                self._faults = {"loggade": [], "aktuella": []}
        return {"status": "connected", "source": self.name,
                "signals": signals, "faults": _slabs_faults_flat(self._faults)}

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        if action == "clear_faults":
            self._faults = {"loggade": [], "aktuella": []}
            self._cleared = 4
            return {"ok": True, "message": "Fault codes cleared (mock)"}
        if action in _SLABS_ACTUATORS:
            return {"ok": True, "message": f"{_SLABS_ACTUATORS[action]} (mock)"}
        return {"ok": False, "error": f"unknown command: {action}"}

    def menu_map(self) -> "list":
        from ..slabs.menu import SLABS_MENU
        return SLABS_MENU


_SLABS_EMPTY_GRACE = 3  # empty bus calls in a row tolerated before reconnect

# ⚠️ SLABS traffic should stay at ~1 Hz — the reference tool's rate in the sniff (keepalive
# `01 3e 3f` every ~1048th ms, reads only on screen refresh). The dashboard's
# poller thread runs at 0.5 s and sent 3E + 21 54 EVERY cycle = 4 frames/s, i.e.
# ~4× the reference. Car 2026-08-18: connected 20:54:28, dead 20:54:49 (21 s).
# The rate is therefore decoupled from the server's poll interval and driven by the clock here.
_SLABS_BUS_PERIOD = 1.0    # seconds between bus calls
_SLABS_FAULT_PERIOD = 30.0  # seconds between fault-code reads (2 extra frames)


class SlabsDataSource(DataSource):
    """Real Wabco SLABS. Establishes fast init 0x29 lazily, re-reads on error.

    Requires a TRANSMITTING K-line cable (KKL/ESP32 master) — not the passive sniff tap.
    """

    name = "slabs"

    def __init__(self, port: str, read_faults: bool = True,
                 raw_log_dir: "str | None" = None) -> None:
        self._port = port
        self._read_faults = read_faults
        self._raw_log_path = _raw_log_path("slabs", raw_log_dir)
        self._slabs = None
        self._faults: "list[str]" = []
        self._tick = 0
        self.fault_every = 10  # read fault codes every Nth poll (1 = "fault watch", every cycle)
        self.on_progress = None  # callback(str): live status during blocking establishment
        self._empty_streak = 0  # number of polls in a row without a reply (grace before reconnect)
        self._last_signals: "dict" = {}  # last decoded signals (shown during the grace period)
        self._last_bus = 0.0    # monotonic time of the last bus call (the 1 Hz throttle)
        self._last_fault = 0.0  # monotonic time of the last fault-code read
        self._raws: "dict[int, bytes]" = {}   # last read raw bytes per LID (store decoding)
        self._extra_lids: "list[int]" = []    # the other store LIDs to rotate through
        self._rot = 0                          # rotation index

    def is_connected(self) -> bool:
        return self._slabs is not None

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..slabs import SLABS_ADDRESS, Slabs

        if self.on_progress:
            self.on_progress("opening the cable")
        port = resolve_serial_port(self._port)
        slabs = Slabs(KWP2000(KLine(_transport(port, self._raw_log_path), target=SLABS_ADDRESS),
                              tolerant=True))
        slabs.open()
        slabs.establish(progress=self.on_progress, **_sleep_kw(self.on_sleep))
        # The other LIDs the store cares about (the 0x54 heights are read every cycle; the rest
        # are rotated ONE per cycle so traffic stays at ~1 Hz). A new mapping in
        # slabs.json → a new field in the UI without a code change.
        # Full reference tool coverage in the rotation: all LIDs the reference tool polls (mapped +
        # unmapped), ONE per cycle so the poll stays light (0x54 is read every cycle anyway).
        # Unmapped ones aren't decoded but are captured in the raw log for future mapping.
        self._extra_lids = sorted(
            (_SLABS_COVERAGE | {sig.lid for sig in load_signals("slabs")}) - {0x54})
        return slabs

    def disconnect(self) -> None:
        # release() — SLABS has no session to end (no-op), but the symmetry makes
        # a module switch look the same regardless of source.
        try:
            if self._slabs is not None:
                self._slabs.release()
        except Exception:  # noqa: BLE001
            pass
        self._slabs = None

    def poll(self) -> "dict":
        try:
            if self._slabs is None:
                self._slabs = self._connect()
                self._empty_streak = 0  # fresh session → full grace before the next reconnect
            now = time.monotonic()
            if now - self._last_bus < _SLABS_BUS_PERIOD:
                # Too soon for more traffic — the server polls faster than SLABS can take.
                # Return the last read values untouched (they're at most 1 s old, which
                # is exactly the resolution the module gives anyway). NO bus calls here.
                return {"status": "connected", "source": self.name,
                        "signals": self._last_signals, "faults": self._faults}
            self._last_bus = now
            try:
                self._slabs.tester_present()  # keepalive — best effort, not a sign of life
            except Exception:  # noqa: BLE001 — a dropped 3E must not tear down the session
                pass
            # LIGHT poll: heights (21 54) EVERY cycle + ONE rotating extra LID from
            # the store. This keeps traffic at ~1 Hz (3E + 2 reads) — far below
            # the block reading that killed the session (5 LIDs × every 0.5 s cycle).
            # The reference tool ran ~1 Hz keepalive + occasional reads.
            try:
                raw = self._slabs.read_data(0x54)  # byte0=left height, byte1=right
            except Exception:  # noqa: BLE001 — a single dropped read
                raw = b""
            if raw:
                self._raws[0x54] = raw
            if self._extra_lids:  # one extra LID per cycle, rotating
                lid = self._extra_lids[self._rot % len(self._extra_lids)]
                self._rot += 1
                try:
                    extra = self._slabs.read_data(lid)
                    if extra:
                        self._raws[lid] = extra
                except Exception:  # noqa: BLE001 — a dropped extra read is harmless
                    pass
            if not raw:
                # A full reconnect costs ~20 s, so we don't tear down the session right away:
                # SLABS often goes quiet for a cycle (bus glitch, or the car started rolling).
                # Keep the session for a couple of polls and show the last known values
                # ("stale"); only after several empties in a row do we give up and reconnect.
                self._empty_streak += 1
                if self._empty_streak < _SLABS_EMPTY_GRACE:
                    return {"status": "connected", "source": self.name, "stale": True,
                            "signals": self._last_signals, "faults": self._faults}
                raise RuntimeError(
                    f"no SLABS response for {self._empty_streak} polls — lost session")
            self._empty_streak = 0
            signals = _slabs_sig(_slabs_decode_store(self._raws))
            self._last_signals = signals  # save for the grace period on an empty cycle
            # Fault codes cost two extra frames (21 11 + 21 47) → their own, very slow
            # cadence in SECONDS. A global fault-watch must not speed up SLABS.
            if self._read_faults and (now - self._last_fault) >= _SLABS_FAULT_PERIOD:
                self._last_fault = now
                try:
                    self._faults = _slabs_faults_flat(self._slabs.read_faults())
                except Exception:  # noqa: BLE001
                    pass
            self._tick += 1
            return {"status": "connected", "source": self.name,
                    "signals": signals, "faults": self._faults}
        except Exception as exc:  # noqa: BLE001
            try:
                if self._slabs is not None:
                    self._slabs.release()  # tear down the link (82) — otherwise 7F 81 10 on reconnect
            except Exception:  # noqa: BLE001
                pass
            self._slabs = None
            return {"status": "error", "source": self.name, "signals": {}, "faults": [],
                    "error": f"{type(exc).__name__}: {exc}"}

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        if action == "read_block":
            return _read_block_cmd(self._slabs, params)
        if self._slabs is None:
            return {"ok": False, "error": "not connected to SLABS"}
        try:
            if action == "clear_faults":
                self._slabs.clear_faults()
                self._tick = 0
                return {"ok": True, "message": "Fault codes cleared"}
            if action in _SLABS_ACTUATORS:
                _slabs_do(self._slabs, action)
                return {"ok": True, "message": f"{_SLABS_ACTUATORS[action]} ✓"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": False, "error": f"unknown command: {action}"}

    def menu_map(self) -> "list":
        from ..slabs.menu import SLABS_MENU
        return SLABS_MENU
