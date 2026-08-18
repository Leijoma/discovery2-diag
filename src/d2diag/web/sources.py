"""Datakällor för dashboarden.

En ``DataSource`` levererar en ögonblicksbild (``poll()``) med status, signaler
(namn → värde/enhet) och felkoder. ``MockDataSource`` simulerar en bil för
UI-utveckling utan hårdvara. ``Td5DataSource`` läser den riktiga Td5-ECU:n.
"""
from __future__ import annotations

import abc
import glob
import math
import random

from ..signals import load_signals
from ..td5.identifiers import BY_NAME, signal_status

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
        if name.startswith(("speed_", "volt_")):
            return "kandidat"        # hjulhastighet/spänning: skala ej bekräftad
    return "belagt"


def _sig(values: "dict[str, float]", module: str = "td5") -> "dict[str, dict]":
    """Paketera {namn: värde} → {namn: {"v", "u", "s", "c"}} (c = confidence)."""
    conf = _conf_map(module)
    out = {}
    for k, v in values.items():
        vr = round(v, 2)
        out[k] = {"v": vr, "u": UNITS.get(k, ""), "s": signal_status(k, vr),
                  "c": _conf_of(module, k, conf)}
    return out


class DataSource(abc.ABC):
    """Kontrakt: ``poll()`` returnerar en färsk snapshot-dict."""

    name: str = "source"
    on_progress = None  # callback(str): live-status under blockande etablering (bas: ingen)

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

    def __init__(self, port: str, read_faults: bool = True) -> None:
        self._port = port
        self._read_faults = read_faults
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
        from ..transport import SerialTransport

        if self.on_progress:
            self.on_progress("opening the cable")
        port = resolve_serial_port(self._port)  # autodetektera vid varje försök
        td5 = Td5(KWP2000(KLine(SerialTransport(port, timeout=1.0)), tolerant=True))
        td5.open()
        td5.establish(progress=self.on_progress)
        return td5

    def disconnect(self) -> None:
        try:
            if self._td5 is not None:
                self._td5.close()
        except Exception:  # noqa: BLE001
            pass
        self._td5 = None

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
                    self._td5.close()
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
        return {"ok": False, "error": f"unknown command: {action}"}


# --- SLABS (Wabco ABS/SLS) ------------------------------------------------ #
_SLABS_UNITS = {"height_left_mm": "mm", "height_right_mm": "mm"}


def _slabs_sig(values: "dict[str, float]") -> "dict[str, dict]":
    conf = _conf_map("slabs")
    return {k: {"v": round(v, 1), "u": _SLABS_UNITS.get(k, ""), "s": None,
                "c": _conf_of("slabs", k, conf)}
            for k, v in values.items()}


def _slabs_faults_flat(f: "dict[str, list]") -> "list[str]":
    """{"loggade":[…],"aktuella":[…]} → platt lista med (Logged)/(Current)-taggar."""
    return [x + " (Logged)" for x in f.get("loggade", [])] + \
           [x + " (Current)" for x in f.get("aktuella", [])]


# Ställdons-actions (webb → SLABS). Namn → svensk etikett (för mock-svar/UI).
_SLABS_ACTUATORS = {
    "buzzer": "SLS buzzer", "compressor": "Compressor", "exhaust": "Exhaust valve",
    "pump_on": "ABS pump on", "pump_off": "ABS pump off",
    "raise_left": "Raise left", "raise_right": "Raise right",
    "lower_left": "Lower left", "lower_right": "Lower right",
    "wheel_fl": "Valve test FL", "wheel_fr": "Valve test FR",
    "wheel_rl": "Valve test RL", "wheel_rr": "Valve test RR",
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
        for w in ("fl", "fr", "rl", "rr"):  # hjul: hastighet (0 stillastående) + givarspänning
            vals[f"speed_{w}"] = 0.0
            vals[f"volt_{w}"] = round(2.2 + random.uniform(-0.05, 0.05), 2)
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


_SLABS_EMPTY_GRACE = 3  # tomma pollar i rad som tolereras innan reconnect (~1,5 s)


class SlabsDataSource(DataSource):
    """Riktig Wabco SLABS. Etablerar fast init 0x29 lazily, läser om vid fel.

    Kräver en SÄNDANDE K-line-kabel (KKL/ESP32-master) — inte den passiva sniff-tappen.
    """

    name = "slabs"

    def __init__(self, port: str, read_faults: bool = True) -> None:
        self._port = port
        self._read_faults = read_faults
        self._slabs = None
        self._faults: "list[str]" = []
        self._tick = 0
        self.fault_every = 10  # läs felkoder var N:e poll (1 = "fault watch", varje cykel)
        self.on_progress = None  # callback(str): live-status under blockande etablering
        self._empty_streak = 0  # antal pollar i rad utan svar (nåd innan reconnect)
        self._last_signals: "dict" = {}  # senaste avkodade signaler (visas under nåd-perioden)

    def is_connected(self) -> bool:
        return self._slabs is not None

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..slabs import SLABS_ADDRESS, Slabs
        from ..transport import SerialTransport

        if self.on_progress:
            self.on_progress("opening the cable")
        port = resolve_serial_port(self._port)
        slabs = Slabs(KWP2000(KLine(SerialTransport(port, timeout=1.0), target=SLABS_ADDRESS),
                              tolerant=True))
        slabs.open()
        slabs.establish(progress=self.on_progress)
        return slabs

    def disconnect(self) -> None:
        try:
            if self._slabs is not None:
                self._slabs.close()
        except Exception:  # noqa: BLE001
            pass
        self._slabs = None

    def poll(self) -> "dict":
        try:
            if self._slabs is None:
                self._slabs = self._connect()
                self._empty_streak = 0  # färsk session → full nåd innan nästa reconnect
            try:
                self._slabs.tester_present()  # keepalive — bästa försök, inte livstecken
            except Exception:  # noqa: BLE001 — ett tappat 3E ska inte riva sessionen
                pass
            # LÄTT poll — bevisat stabilt (sniff 2026-08-07): bara höjder (21 54).
            # SLABS tål inte att block-pollas med många LID:er i varje 0.5 s-cykel;
            # reference tool körde ~1 Hz keepalive + enstaka läsningar. Store-driven
            # block-läsning fanns här men destabiliserade sessionen (~7× busstrafik).
            try:
                raw = self._slabs.read_data(0x54)  # byte0=vänster höjd, byte1=höger
            except Exception:  # noqa: BLE001 — en enstaka tappad läsning
                raw = b""
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
            hl = raw[0] if len(raw) > 0 else 0
            hr = raw[1] if len(raw) > 1 else 0
            signals = _slabs_sig({
                "height_left": hl, "height_right": hr,
                "height_left_mm": hl * 1.4, "height_right_mm": hr * 1.4,
            })
            self._last_signals = signals  # spara för nåd-perioden vid en tom cykel
            # Felkoder på LÄTT kadens: aldrig oftare än var 10:e poll (~5 s) även när
            # global fault-watch är på — SLABS-bussen tål inte snabb fel-pollning.
            every = max(self.fault_every, 10)
            if self._read_faults and self._tick % every == 0:
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
                    self._slabs.close()
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
