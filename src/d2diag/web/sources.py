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

from ..td5.identifiers import BY_NAME

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
    """Paketera {namn: värde} → {namn: {"v": värde, "u": enhet}}."""
    return {k: {"v": round(v, 2), "u": UNITS.get(k, "")} for k, v in values.items()}


class DataSource(abc.ABC):
    """Kontrakt: ``poll()`` returnerar en färsk snapshot-dict."""

    name: str = "source"

    @abc.abstractmethod
    def poll(self) -> "dict":
        """Returnera {status, signals, faults, error?}."""

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

    def poll(self) -> "dict":
        try:
            if self._td5 is None:
                self._td5 = self._connect()
            signals = self._td5.read_all()
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
