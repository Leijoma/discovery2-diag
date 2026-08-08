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

from ..td5.identifiers import BY_NAME, signal_status

# Chip-ledtrådar för att känna igen en KKL/OBD-kabel bland flera USB-seriella enheter.
_KKL_HINTS = ("ft232", "ftdi", "ch340", "cp210", "usb-serial", "usb_uart", "obd", "kkl")


def resolve_serial_port(spec: "str | None") -> str:
    """Returnera en konkret serieport.

    ``spec`` som är en riktig sökväg returneras oförändrad. ``None`` eller
    ``"auto"`` autodetekterar en USB-seriell enhet — föredrar de **stabila**
    ``/dev/serial/by-id/``-länkarna (helst en känd KKL-chip), sedan ``ttyUSB*`` /
    ``ttyACM*``. Höjer :class:`FileNotFoundError` om ingen hittas (t.ex. kabeln
    inte inkopplad än) — anropas om vid varje anslutningsförsök.
    """
    if spec and spec != "auto":
        return spec
    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    preferred = [p for p in by_id if any(h in p.lower() for h in _KKL_HINTS)]
    for candidates in (preferred, by_id,
                       sorted(glob.glob("/dev/ttyUSB*")),
                       sorted(glob.glob("/dev/ttyACM*"))):
        if candidates:
            return candidates[0]
    raise FileNotFoundError("ingen USB-seriell enhet hittad (KKL ej ansluten?)")

# Enhetskarta från identifier-tabellen (namn → enhet).
UNITS = {name: sig.unit for name, sig in BY_NAME.items()}


def _sig(values: "dict[str, float]") -> "dict[str, dict]":
    """Paketera {namn: värde} → {namn: {"v", "u", "s"}} där s = ok/low/high/None."""
    out = {}
    for k, v in values.items():
        vr = round(v, 2)
        out[k] = {"v": vr, "u": UNITS.get(k, ""), "s": signal_status(k, vr)}
    return out


class DataSource(abc.ABC):
    """Kontrakt: ``poll()`` returnerar en färsk snapshot-dict."""

    name: str = "source"

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
        return {"ok": False, "error": f"okänt kommando: {action}"}


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
            return {"ok": True, "message": "Felkoder raderade (mock)"}
        return {"ok": False, "error": f"okänt kommando: {action}"}

    def menu_map(self) -> "list":
        from ..td5.menu import TD5_MENU
        return TD5_MENU


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

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..td5 import Td5
        from ..transport import SerialTransport

        port = resolve_serial_port(self._port)  # autodetektera vid varje försök
        td5 = Td5(KWP2000(KLine(SerialTransport(port, timeout=1.0)), tolerant=True))
        td5.open()
        td5.establish()
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
                raise RuntimeError("inga signaler lästes — brus eller tappad kontakt")
            # läs felkoder mer sällan (dyrt); var ~10:e poll
            if self._read_faults and self._fault_tick % 10 == 0:
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
        if action == "clear_faults":
            if self._td5 is None:
                return {"ok": False, "error": "inte ansluten till ECU:n"}
            try:
                self._td5.clear_faults()
                self._fault_tick = 0  # tvinga om-läsning av felkoder nästa poll
                return {"ok": True, "message": "Felkoder raderade"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": False, "error": f"okänt kommando: {action}"}


# --- SLABS (Wabco ABS/SLS) ------------------------------------------------ #
_SLABS_UNITS = {"height_left_mm": "mm", "height_right_mm": "mm"}


def _slabs_sig(values: "dict[str, float]") -> "dict[str, dict]":
    return {k: {"v": round(v, 1), "u": _SLABS_UNITS.get(k, ""), "s": None}
            for k, v in values.items()}


def _slabs_faults_flat(f: "dict[str, list]") -> "list[str]":
    """{"loggade":[…],"aktuella":[…]} → platt lista med (Logged)/(Current)-taggar."""
    return [x + " (Logged)" for x in f.get("loggade", [])] + \
           [x + " (Current)" for x in f.get("aktuella", [])]


# Ställdons-actions (webb → SLABS). Namn → svensk etikett (för mock-svar/UI).
_SLABS_ACTUATORS = {
    "buzzer": "SLS-summer", "compressor": "Kompressor", "exhaust": "Avluftningsventil",
    "pump_on": "ABS-pump på", "pump_off": "ABS-pump av",
    "raise_left": "Höj vänster", "raise_right": "Höj höger",
    "lower_left": "Sänk vänster", "lower_right": "Sänk höger",
    "wheel_fl": "Ventiltest VF", "wheel_fr": "Ventiltest HF",
    "wheel_rl": "Ventiltest VB", "wheel_rr": "Ventiltest HB",
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
        raise ValueError(f"okänt kommando: {action}")


class MockSlabsDataSource(DataSource):
    """Simulerad SLABS för UI-dev: rörliga höjder + baslinjens två loggade fel."""

    name = "slabs"

    def __init__(self) -> None:
        self._t = 0.0
        self._faults = {
            "loggade": [
                "020: höger fram hjulhastighetsgivare — output too low",
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
            return {"ok": True, "message": "Felkoder raderade (mock)"}
        if action in _SLABS_ACTUATORS:
            return {"ok": True, "message": f"{_SLABS_ACTUATORS[action]} (mock)"}
        return {"ok": False, "error": f"okänt kommando: {action}"}

    def menu_map(self) -> "list":
        from ..slabs.menu import SLABS_MENU
        return SLABS_MENU


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

    def _connect(self):
        from ..kline import KLine
        from ..kwp2000 import KWP2000
        from ..slabs import SLABS_ADDRESS, Slabs
        from ..transport import SerialTransport

        port = resolve_serial_port(self._port)
        slabs = Slabs(KWP2000(KLine(SerialTransport(port, timeout=1.0), target=SLABS_ADDRESS),
                              tolerant=True))
        slabs.open()
        slabs.establish()
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
            self._slabs.tester_present()
            h = self._slabs.read_data(0x54)  # höjder: byte0=vänster, byte1=höger
            hl = h[0] if len(h) > 0 else 0
            hr = h[1] if len(h) > 1 else 0
            vals = {
                "height_left": hl, "height_right": hr,
                "height_left_mm": hl * 1.4, "height_right_mm": hr * 1.4,
            }
            try:
                sp = self._slabs.read_data(0x43)  # 4 hjulhastigheter (7c 00-mönster)
                vo = self._slabs.read_data(0x50)  # 4 givarspänningar (rå ADC)
                for i, w in enumerate(("fl", "fr", "rl", "rr")):  # ordning preliminär
                    vals[f"speed_{w}"] = sp[i * 2] if len(sp) > i * 2 else 0
                    vals[f"volt_{w}"] = round(vo[i] * 0.02, 2) if len(vo) > i else 0
            except Exception:  # noqa: BLE001 — hjuldata är best-effort
                pass
            signals = _slabs_sig(vals)
            if self._read_faults and self._tick % 10 == 0:
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
        if self._slabs is None:
            return {"ok": False, "error": "inte ansluten till SLABS"}
        try:
            if action == "clear_faults":
                self._slabs.clear_faults()
                self._tick = 0
                return {"ok": True, "message": "Felkoder raderade"}
            if action in _SLABS_ACTUATORS:
                _slabs_do(self._slabs, action)
                return {"ok": True, "message": f"{_SLABS_ACTUATORS[action]} ✓"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": False, "error": f"okänt kommando: {action}"}

    def menu_map(self) -> "list":
        from ..slabs.menu import SLABS_MENU
        return SLABS_MENU
