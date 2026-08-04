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
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def log(self, snapshot: "dict") -> None:
        """Skriv en rad om felkoderna ändrats ELLER throttle-intervallet passerat."""
        faults = snapshot.get("faults", [])
        changed = faults != self._last_faults
        now = time.monotonic()
        if not changed and (now - self._last_write) < self._min_interval:
            return
        self._last_write = now
        self._last_faults = list(faults)
        row = {
            "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "status": snapshot.get("status"),
            "signals": {k: v.get("v") for k, v in snapshot.get("signals", {}).items()},
            "faults": faults,
        }
        if changed:
            row["fault_change"] = True
        if snapshot.get("error"):
            row["error"] = snapshot["error"]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
