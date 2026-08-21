"""Datakällor för dashboarden.

En ``DataSource`` levererar en ögonblicksbild (``poll()``) med status, signaler
(namn → värde/enhet) och felkoder. ``MockDataSource`` simulerar en bil för
UI-utveckling utan hårdvara. ``Td5DataSource`` läser den riktiga Td5-ECU:n.
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
    """Sökväg för en rå TX/RX-logg, eller None om råloggning är av.

    En fil per modul och dashboard-start (``raw-<modul>-<tid>.log``).
    LoggingTransport öppnar i append-läge, så återanslutningar (modulbyte,
    fel-retry) fortsätter i SAMMA fil — en obruten busslogg för mappning."""
    if not raw_log_dir:
        return None
    os.makedirs(raw_log_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(raw_log_dir, f"raw-{module}-{stamp}.log")


def _transport(port: str, raw_log_path: "str | None"):
    """SerialTransport, ev. inlindad i LoggingTransport för rå TX/RX-logg.

    Lazy import så Mock-källorna kan köras utan pyserial. Är råloggning på ligger
    LoggingTransport transparent under KLine och fångar varje byte åt bägge håll."""
    from ..transport import SerialTransport
    inner = SerialTransport(port, timeout=1.0)
    if raw_log_path:
        from ..transport import LoggingTransport
        return LoggingTransport(inner, logfile=raw_log_path)
    return inner


# Full reference tool-täckning: läs även LID:er reference tool pollar men vi ännu inte mappat, så
# råloggen fångar ALL tillgänglig data — då kan omappade fält hittas ur en vanlig
# körning (så hittades MAF i 1D 2026-08-21). "Kasta inte bort de bytes vi inte döpt."
#
# TD5 (ej sessionskänslig): läs extra-LID:erna VARJE cykel så de samplas jämte rpm
# för korrelation. 1E/1F/20 = bekräftat svarande i fuelling-blocket (lid_sweep
# 2026-08-21). 37/38 = KANDIDATER från SimonRafferty/Td5-Arduino (EGR- resp
# wastegate-position, %) — OVERIFIERADE, fångas i råloggen för att bekräftas mot
# bilen (EGR-positionen är relevant för RDL016:s EGR-fel 001-07).
_TD5_COVERAGE_EXTRA = (0x1E, 0x1F, 0x20, 0x37, 0x38)
# SLABS (MÅSTE pollas lätt — block-läsning dödar sessionen): dessa LID:er roteras
# EN per cykel (0x54-höjderna läses ändå varje cykel). Källa: slabs/menu.py +
# references/reference_tool_menu_map.md (reference tool-menyns input-block).
_SLABS_COVERAGE = frozenset({
    0x11, 0x3B, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x50, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
})

# Bränsledator: härledda fält ur injektionsmängd + varvtal + fart. Ej LID-läsning →
# enhet + confidence anges här (injection_qty är kandidat, så förbrukningen med).
_INJ_PER_REV = 2.5          # 5-cyl 4-takt: 5/2 insprutningar per vevaxelvarv
_DIESEL_G_PER_L = 832.0     # diesel densitet
_DERIVED_TD5 = {
    "fuel_rate":        ("L/h", "kandidat"),
    "economy":          ("L/100km", "kandidat"),
    "trip_economy":     ("L/100km", "kandidat"),
    "lifetime_economy": ("L/100km", "kandidat"),
}


class _FuelComputer:
    """Momentan förbrukning + trip- och livstidssnitt ur injektionsmängd (mg/stroke),
    varvtal och fart. Integrerar med VERKLIG tid mellan pollar (time.monotonic).

    L/h = inj[mg/stroke] × insprutn/varv × rpm × 60 / 1e6 / (densitet g/ml).
    Trip = sedan objektet skapades (dashboard-start). Livstid = persistad i fil.
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
        """Nolla klockan (vid modulbyte/reconnect) så en lucka inte integreras."""
        self._last = None

    def update(self, inj_mg: "float | None", rpm: "float | None",
               speed_kmh: "float | None") -> "dict":
        now = self._clock()
        rate = None
        if inj_mg is not None and rpm:
            rate = inj_mg * _INJ_PER_REV * rpm * 60.0 / 1e6 / (_DIESEL_G_PER_L / 1000.0)
        if self._last is not None and rate is not None:
            dt_h = min(now - self._last, 3.0) / 3600.0   # cap 3 s → ingen spik efter paus
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
            if speed_kmh and speed_kmh > 5:                 # ekonomi bara i rörelse
                out["economy"] = round(rate / speed_kmh * 100.0, 1)
        if self._trip_dist > 0.1:
            out["trip_economy"] = round(self._trip_fuel / self._trip_dist * 100.0, 1)
        if self._life_dist > 1.0:
            out["lifetime_economy"] = round(self._life_fuel / self._life_dist * 100.0, 1)
        self._tick += 1
        if self._tick % 60 == 0:                            # persist livstid ~var 30-60 s
            self._save()
        return out

# Chip-ledtrådar för att känna igen en KKL/OBD-kabel bland flera USB-seriella enheter.
_KKL_HINTS = ("ft232", "ftdi", "ch340", "cp210", "usb-serial", "usb_uart", "obd", "kkl")


# macOS call-out-portar (använd cu.*, ALDRIG tty.* — tty blockar på DCD).
_MAC_GLOBS = (
    "/dev/cu.usbserial-*", "/dev/cu.usbmodem*",
    "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*",
)


def resolve_serial_port(spec: "str | None") -> str:
    """Returnera en konkret serieport.

    ``spec`` som är en riktig sökväg returneras oförändrad. ``None`` eller
    ``"auto"`` autodetekterar en USB-seriell enhet. Ordning: **stabila**
    ``/dev/serial/by-id/``-länkar (Linux) → ``/dev/cu.*`` (macOS) → ``ttyUSB*`` /
    ``ttyACM*``. Inom by-id och cu.* föredras en känd KKL-chip (``_KKL_HINTS``).
    Höjer :class:`FileNotFoundError` om ingen hittas (t.ex. kabeln inte inkopplad
    än) — anropas om vid varje anslutningsförsök.
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

# Enhetskarta från identifier-tabellen (namn → enhet).
UNITS = {name: sig.unit for name, sig in BY_NAME.items()}


def _conf_map(module: str) -> "dict[str, str]":
    """{signalnamn → confidence} ur signalstoren (belagt/kandidat)."""
    return {s.name: s.confidence for s in load_signals(module)}


def _conf_of(module: str, name: str, conf: "dict[str, str]") -> str:
    """Confidence för en signal — ur storen, annars heuristik för härledda fält.
    Trust-vyn (Verified/Explorer) filtrerar på detta."""
    if name in conf:
        return conf[name]
    if module == "slabs":
        if name.startswith("height_"):
            return "belagt"          # härledd ur belagd höjd
        if name.startswith(("wheel_speed_", "abs_sensor_")):
            return "kandidat"        # hjulhastighet/spänning: skala ej bekräftad
    return "belagt"


def _sig(values: "dict[str, float]", module: str = "td5") -> "dict[str, dict]":
    """Paketera {namn: värde} → {namn: {"v", "u", "s", "c"}} (c = confidence)."""
    conf = _conf_map(module)
    out = {}
    for k, v in values.items():
        vr = round(v, 2)
        if k in _DERIVED_TD5:                # beräknade fält (bränsledator)
            unit, c = _DERIVED_TD5[k]
        else:
            unit, c = UNITS.get(k, ""), _conf_of(module, k, conf)
        out[k] = {"v": vr, "u": unit, "s": signal_status(k, vr), "c": c}
    return out


def _sleep_kw(hook) -> "dict":
    """``{"sleep": hook}`` om en hook finns, annars tomt (behåll time.sleep)."""
    return {} if hook is None else {"sleep": hook}


class DataSource(abc.ABC):
    """Kontrakt: ``poll()`` returnerar en färsk snapshot-dict."""

    name: str = "source"
    on_progress = None  # callback(str): live-status under blockande etablering (bas: ingen)
    # sleep-hook för etableringens väntetider (SLABS tysta period är 28 s). Servern
    # sätter en avbrytbar variant så ett modulbyte inte behöver vänta ut den.
    on_sleep = None

    def is_connected(self) -> bool:
        """Har källan en levande session? Bas: nej (mock rapporterar alltid connected via poll)."""
        return False

    @abc.abstractmethod
    def poll(self) -> "dict":
        """Returnera {status, signals, faults, error?}."""

    def disconnect(self) -> None:
        """Släpp ev. K-line-session/port (vid modulbyte). Bas: inget att göra."""

    def menu_map(self) -> "list":
        """Referens-/täckningskarta (reference tool-meny + vår status). Bas: tom."""
        return []

    def command(self, action: str, params: "dict | None" = None) -> "dict":
        """Utför ett skrivkommando. Bas: okänt. Returnerar {ok, message|error}.

        Körs i pollertråden (serialiserat med poll) så K-line-åtkomsten aldrig
        krockar. Skrivningar mot ECU:n är känsliga — bara uttryckligt stödda
        åtgärder tillåts; riskabla (ställdonstester, settings) exponeras inte här.
        """
        return {"ok": False, "error": f"unknown command: {action}"}


class MockDataSource(DataSource):
    """Simulerad bil för UI-dev: rimliga, rörliga värden + ett aktivt fel."""

    name = "mock"

    _ACTIVE_FAULT = "inlet air temp. circuit (Current)"
    _LOGGED_FAULT = "air flow circuit (Logged Low)"

    def __init__(self) -> None:
        self._t = 0.0
        self._coolant = 20.0  # kallstart, värms upp
        self._faults = [self._LOGGED_FAULT, self._ACTIVE_FAULT]
        self._cleared_ticks = 0  # >0 = nyss raderat, felen tillfälligt borta

    def poll(self) -> "dict":
        self._t += 1
        # tomgång med lite variation, och en "gaspådrag"-puls då och då
        revving = (int(self._t) % 30) in (10, 11, 12, 13)
        base = 2200 if revving else 800
        rpm = base + random.uniform(-40, 60)
        speed = max(0.0, (rpm - 800) / 45) if revving else 0.0
        self._coolant = min(88.0, self._coolant + 0.15)  # kryper mot arbetstemp
        manifold = 1.0 + (0.25 if revving else 0.0) + random.uniform(-0.01, 0.01)
        signals = {
            "rpm": rpm,
            "speed": speed,
            "battery": 14.1 + random.uniform(-0.15, 0.15),
            "coolant_temp": self._coolant,
            "air_temp": 120.0,  # låst → speglar IAT-felet på riktiga bilen
            "fuel_temp": self._coolant - 6 + random.uniform(-1, 1),
            "manifold_press": manifold,
            "ambient_press_1": 1.01,
            "rpm_error": random.uniform(-8, 8),
            "balance_1": random.uniform(-4, 4),
            "balance_2": random.uniform(-4, 4),
            "balance_3": random.uniform(-4, 4),
            "balance_4": random.uniform(-4, 4),
            "balance_5": random.uniform(-4, 4),
        }
        # Efter radering är listan tom några polls, sen återkommer det AKTIVA
        # felet (fortfarande fel) — demonstrerar "radera och se om det kommer igen".
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
            self._cleared_ticks = 4  # tomt i ~4 polls, sen återkommer aktivt fel
            return {"ok": True, "message": "Fault codes cleared (mock)"}
        return {"ok": False, "error": f"unknown command: {action}"}

    def menu_map(self) -> "list":
        from ..td5.menu import TD5_MENU
        return TD5_MENU


def _read_block_cmd(session, params: "dict | None") -> "dict":
    """Läs en LID-uppsättning via en live-session → {ok, raws:{lidhex:hex}}.

    Read-only-primitiven bakom den aktiva differential-mappningen i Karta-fliken
    (baslinje/läs-igen). Delas av Td5- och SLABS-källorna."""
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
    """Riktig Td5-ECU. Etablerar session lazily och läser om vid fel.

    Kräver hårdvara; importerar tunga beroenden lokalt så Mock kan köras fristående.
    """

    name = "td5"

    def __init__(self, port: str, read_faults: bool = True,
                 raw_log_dir: "str | None" = None,
                 fuel_state_path: "str | None" = None) -> None:
        self._port = port
        self._read_faults = read_faults
        self._raw_log_path = _raw_log_path("td5", raw_log_dir)
        self._fuel = _FuelComputer(fuel_state_path)  # bränsledator (momentan/trip/livstid)
        self._td5 = None
        self._faults: "list[str]" = []
        self._fault_tick = 0
        self.fault_every = 10  # läs felkoder var N:e poll (1 = "fault watch", varje cykel)
        self.on_progress = None  # callback(str): live-status under blockande etablering

    def is_connected(self) -> bool:
        return self._td5 is not None

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..td5 import Td5

        if self.on_progress:
            self.on_progress("opening the cable")
        port = resolve_serial_port(self._port)  # autodetektera vid varje försök
        td5 = Td5(KWP2000(KLine(_transport(port, self._raw_log_path)), tolerant=True))
        td5.open()
        td5.establish(progress=self.on_progress, **_sleep_kw(self.on_sleep))
        return td5

    def disconnect(self) -> None:
        # release() = StopDiagnosticSession + close. Bara close() lämnar TD5-sessionen
        # öppen på den delade bussen → nästa modul (SLABS) får 7F 81 10 på sin init.
        try:
            if self._td5 is not None:
                self._td5.release()
        except Exception:  # noqa: BLE001
            pass
        self._td5 = None
        self._fuel.pause()  # nolla bränsledatorns klocka så reconnect-luckan inte räknas

    def menu_map(self) -> "list":
        from ..td5.menu import TD5_MENU
        return TD5_MENU

    def poll(self) -> "dict":
        try:
            if self._td5 is None:
                self._td5 = self._connect()
            signals = self._td5.read_all()
            if not signals:
                # sessionen "uppe" men alla läsningar föll (brus/tappad kabel) →
                # behandla som tappad kontakt så vi återansluter nästa poll.
                raise RuntimeError("no signals read — noise or lost connection")
            # Full täckning: läs omappade LID:er reference tool pollar → hamnar i råloggen
            # (avkodas inte, men fångas för framtida mappning). Fel här får inte
            # fälla pollen — read_all lyckades redan.
            try:
                self._td5.read_block(_TD5_COVERAGE_EXTRA)
            except Exception:  # noqa: BLE001
                pass
            # Bränsledator: momentan L/h + L/100km, trip- och livstidssnitt, ur
            # injektionsmängd + varvtal + fart. Härledda fält, integreras över tid.
            signals.update(self._fuel.update(
                signals.get("injection_qty"), signals.get("rpm"), signals.get("speed")))
            # läs felkoder mer sällan (dyrt); var ~10:e poll
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
        except Exception as exc:  # noqa: BLE001 — tappa sessionen och återanslut nästa poll
            try:
                if self._td5 is not None:
                    self._td5.release()  # riv länken (82) — annars 7F 81 10 vid reconnect
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
                self._fault_tick = 0  # tvinga om-läsning av felkoder nästa poll
                return {"ok": True, "message": "Fault codes cleared"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        # Output-tester (IOControl) + injektorpuls. Belagda ur sniff 2026-08-08 men
        # ALDRIG körda från vår kod mot bilen → experimentella tills verifierade.
        # Hårdvaruskrivningar: UI gatar bakom bekräftelse.
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
    """Avkoda alla SLABS-store-fält vi har rå-bytes för → {namn: värde}.

    Store-driven, så en ny bekräftad mappning i ``slabs.json`` dyker upp i UI:t
    utan kodändring. Höjderna kompletteras med härledda mm-fält (SVG-bilen). Fält
    med tillståndsetikett (any_door) tas INTE med här — de går som numeriskt
    0/1 och etiketten sätts i UI-lagret om det behövs.
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
    """{"loggade":[…],"aktuella":[…]} → platt lista med (Logged)/(Current)-taggar."""
    return [x + " (Logged)" for x in f.get("loggade", [])] + \
           [x + " (Current)" for x in f.get("aktuella", [])]


# Ställdons-actions (webb → SLABS). Namn → svensk etikett (för mock-svar/UI).
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
    """Kör en ställdons-action mot ett riktigt Slabs-objekt."""
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
    """Simulerad SLABS för UI-dev: rörliga höjder + baslinjens två loggade fel."""

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
        for w in ("fl", "fr", "rl", "rr"):  # hjul: hastighet (~124 råvärde stilla) + givarspänning
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


_SLABS_EMPTY_GRACE = 3  # tomma bussanrop i rad som tolereras innan reconnect

# ⚠️ SLABS-trafiken ska ligga på ~1 Hz — reference tools takt i sniffen (keepalive
# `01 3e 3f` var ~1048:e ms, läsningar bara vid skärmuppdatering). Dashboardens
# pollertråd går på 0,5 s och skickade 3E + 21 54 i VARJE cykel = 4 ramar/s, alltså
# ~4× referensen. Bilen 2026-08-18: uppkopplad 20:54:28, död 20:54:49 (21 s).
# Takten frikopplas därför från serverns pollintervall och styrs av klockan här.
_SLABS_BUS_PERIOD = 1.0    # sekunder mellan bussanrop
_SLABS_FAULT_PERIOD = 30.0  # sekunder mellan felkodsläsningar (2 extra ramar)


class SlabsDataSource(DataSource):
    """Riktig Wabco SLABS. Etablerar fast init 0x29 lazily, läser om vid fel.

    Kräver en SÄNDANDE K-line-kabel (KKL/ESP32-master) — inte den passiva sniff-tappen.
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
        self.fault_every = 10  # läs felkoder var N:e poll (1 = "fault watch", varje cykel)
        self.on_progress = None  # callback(str): live-status under blockande etablering
        self._empty_streak = 0  # antal pollar i rad utan svar (nåd innan reconnect)
        self._last_signals: "dict" = {}  # senaste avkodade signaler (visas under nåd-perioden)
        self._last_bus = 0.0    # monotonic-tid för senaste bussanrop (1 Hz-strypningen)
        self._last_fault = 0.0  # monotonic-tid för senaste felkodsläsning
        self._raws: "dict[int, bytes]" = {}   # senast lästa rå-bytes per LID (store-avkodning)
        self._extra_lids: "list[int]" = []    # övriga store-LID:er att rotera igenom
        self._rot = 0                          # rotationsindex

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
        # Övriga LID:er storen bryr sig om (höjderna 0x54 läses varje cykel; resten
        # roteras EN per cykel så trafiken stannar på ~1 Hz). Ny mappning i
        # slabs.json → nytt fält i UI:t utan kodändring.
        # Full reference tool-täckning i rotationen: alla LID:er reference tool pollar (mappade +
        # omappade), EN per cykel så pollen förblir lätt (0x54 läses ändå varje cykel).
        # Omappade avkodas inte men fångas i råloggen för framtida mappning.
        self._extra_lids = sorted(
            (_SLABS_COVERAGE | {sig.lid for sig in load_signals("slabs")}) - {0x54})
        return slabs

    def disconnect(self) -> None:
        # release() — SLABS har ingen session att avsluta (no-op), men symmetrin gör
        # att modulbyte ser likadant ut oavsett källa.
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
                self._empty_streak = 0  # färsk session → full nåd innan nästa reconnect
            now = time.monotonic()
            if now - self._last_bus < _SLABS_BUS_PERIOD:
                # För tidigt för mer trafik — servern pollar snabbare än SLABS tål.
                # Returnera senast lästa värden orört (de är högst 1 s gamla, vilket
                # är precis den upplösning modulen ger ändå). INGA bussanrop här.
                return {"status": "connected", "source": self.name,
                        "signals": self._last_signals, "faults": self._faults}
            self._last_bus = now
            try:
                self._slabs.tester_present()  # keepalive — bästa försök, inte livstecken
            except Exception:  # noqa: BLE001 — ett tappat 3E ska inte riva sessionen
                pass
            # LÄTT poll: höjder (21 54) VARJE cykel + EN roterande extra-LID ur
            # storen. Det håller trafiken på ~1 Hz (3E + 2 läsningar) — långt under
            # den block-läsning som dödade sessionen (5 LID:er × varje 0,5 s-cykel).
            # Reference tool körde ~1 Hz keepalive + enstaka läsningar.
            try:
                raw = self._slabs.read_data(0x54)  # byte0=vänster höjd, byte1=höger
            except Exception:  # noqa: BLE001 — en enstaka tappad läsning
                raw = b""
            if raw:
                self._raws[0x54] = raw
            if self._extra_lids:  # en extra LID per cykel, roterande
                lid = self._extra_lids[self._rot % len(self._extra_lids)]
                self._rot += 1
                try:
                    extra = self._slabs.read_data(lid)
                    if extra:
                        self._raws[lid] = extra
                except Exception:  # noqa: BLE001 — en tappad extra-läsning är ofarlig
                    pass
            if not raw:
                # En full reconnect kostar ~20 s, så vi river inte sessionen direkt:
                # SLABS tystnar ofta en cykel (bussglitch, eller bilen började rulla).
                # Behåll sessionen ett par pollar och visa senaste kända värden
                # ("stale"); först efter flera tomma i rad ger vi upp och kopplar om.
                self._empty_streak += 1
                if self._empty_streak < _SLABS_EMPTY_GRACE:
                    return {"status": "connected", "source": self.name, "stale": True,
                            "signals": self._last_signals, "faults": self._faults}
                raise RuntimeError(
                    f"inget SLABS-svar på {self._empty_streak} pollar — tappad session")
            self._empty_streak = 0
            signals = _slabs_sig(_slabs_decode_store(self._raws))
            self._last_signals = signals  # spara för nåd-perioden vid en tom cykel
            # Felkoder kostar två extra ramar (21 11 + 21 47) → egen, mycket långsam
            # kadens i SEKUNDER. Global fault-watch får inte snabba upp SLABS.
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
                    self._slabs.release()  # riv länken (82) — annars 7F 81 10 vid reconnect
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
