"""Datakällor för dashboarden.

En ``DataSource`` levererar en ögonblicksbild (``poll()``) med status, signaler
(namn → värde/enhet) och felkoder. ``MockDataSource`` simulerar en bil för
UI-utveckling utan hårdvara. ``Td5DataSource`` läser den riktiga Td5-ECU:n.
"""
from __future__ import annotations

import abc
import math
import random

from ..td5.identifiers import BY_NAME

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


class MockDataSource(DataSource):
    """Simulerad bil för UI-dev: rimliga, rörliga värden + ett aktivt fel."""

    name = "mock"

    def __init__(self) -> None:
        self._t = 0.0
        self._coolant = 20.0  # kallstart, värms upp

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
        return {
            "status": "connected",
            "source": self.name,
            "signals": _sig(signals),
            "faults": [
                "air flow circuit (Logged Low)",
                "inlet air temp. circuit (Current)",
            ],
        }


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

        td5 = Td5(KWP2000(KLine(SerialTransport(self._port, timeout=1.0)), tolerant=True))
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
