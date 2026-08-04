"""Loggning av datasnapshots till fil (JSONL) för efteranalys.

En rad = ett JSON-objekt med tidsstämpel, status, signaler (namn→värde) och
felkoder. Skrivningen throttlas (default var 2 s) men sker **alltid direkt när
felkodsuppsättningen ändras** — så intermittenta fel (som kommer/går) fångas med
exakt tidpunkt. Bra för att analysera en körning efteråt.
"""
from __future__ import annotations

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
