"""Loggning av datasnapshots till fil (JSONL) för efteranalys.

En rad = ett JSON-objekt med tidsstämpel, status, signaler (namn→värde) och
felkoder. Skrivningen throttlas (default var 2 s) men sker **alltid direkt när
felkodsuppsättningen ändras** — så intermittenta fel (som kommer/går) fångas med
exakt tidpunkt. Bra för att analysera en körning efteråt.

:class:`CsvLogger` är den **användarvända** loggen: rå CSV av live-data (en kolumn
per signal, enhet i kolumnnamnet) så man kan följa temperaturer, tryck, gaspedal
m.m. i Excel/Sheets under en körning.
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone


class SnapshotLogger:
    def __init__(self, path: str, min_interval: float = 2.0) -> None:
        self.path = path
        self._min_interval = min_interval
        self._last_write = 0.0
        self._last_faults: "list | None" = None
        self._last_anom: "list | None" = None
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def log(self, snapshot: "dict") -> None:
        """Skriv en rad när felkoder ELLER avvikelser ändras, annars throttlat."""
        faults = snapshot.get("faults", [])
        signals = snapshot.get("signals", {})
        anomalies = sorted(k for k, sg in signals.items() if sg.get("s") in ("low", "high"))
        fault_changed = faults != self._last_faults
        anom_changed = anomalies != self._last_anom
        now = time.monotonic()
        if not (fault_changed or anom_changed) and (now - self._last_write) < self._min_interval:
            return
        self._last_write = now
        self._last_faults = list(faults)
        self._last_anom = anomalies
        row = {
            "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "status": snapshot.get("status"),
            "signals": {k: v.get("v") for k, v in signals.items()},
            "faults": faults,
        }
        if anomalies:
            row["anom"] = anomalies
        if fault_changed:
            row["fault_change"] = True
        if snapshot.get("error"):
            row["error"] = snapshot["error"]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class CsvLogger:
    """Append live signal values to a CSV file — for the user to follow temps,
    pressures, accelerator tracks etc. over a drive (opens straight into Excel).

    Columns are **fixed from the first snapshot that has signals** (so the CSV is
    rectangular): column label = ``name (unit)``. Later-missing signals are left
    blank, and signals that appear later are ignored — stable columns beat a ragged
    file. One row per :meth:`log` call; each row is flushed immediately (crash-safe).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.rows = 0
        self._columns: "list[str] | None" = None  # signal names, set on first data row
        self._module: "str | None" = None  # which module the locked columns belong to
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _header(self, signals: "dict") -> "list[str]":
        cols = []
        for name in self._columns or []:
            unit = (signals.get(name) or {}).get("u") or ""
            cols.append(f"{name} ({unit})" if unit else name)
        # ``faults`` column carries the active fault list per row → you can see the
        # exact timestamp a fault appears/clears (e.g. intermittent SLABS faults).
        return ["timestamp", "status", "faults", *cols]

    def log(self, snapshot: "dict") -> None:
        signals = snapshot.get("signals") or {}
        module = snapshot.get("module")
        if self._columns is not None and module != self._module:
            # Modulbyte: de låsta kolumnerna tillhör den gamla modulen, så varje rad
            # skulle bli tom. Rotera till en egen fil per modul i stället.
            self._rotate(module)
        if self._columns is None:
            if not signals:
                return  # wait for real data before locking the header
            self._columns = sorted(signals)
            self._module = module
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self._header(signals))
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        faults = "; ".join(snapshot.get("faults") or [])
        line = [ts, snapshot.get("status", ""), faults]
        for name in self._columns:
            v = (signals.get(name) or {}).get("v")
            line.append("" if v is None else v)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(line)
        self.rows += 1

    def _rotate(self, module: "str | None") -> None:
        """Börja en ny fil för en ny modul: ``…-<modul>.csv``. Radräknaren fortsätter
        (den räknar loggade rader, inte rader per fil)."""
        base = self.path[:-4] if self.path.endswith(".csv") else self.path
        base = base.rsplit("-", 1)[0] if self._module and base.endswith(f"-{self._module}") else base
        self.path = f"{base}-{module or 'unknown'}.csv"
        self._columns = None
        self._module = None

    def status(self) -> "dict":
        return {"recording": True, "file": os.path.basename(self.path), "rows": self.rows}
