"""Passive sniff calibration — read reference tool traffic (RX-only) and map LID fields.

Since our ESP32 tap never transmits, the reference tool must be connected and polling;
we decode passively and compare against the reference tool's screen to solve scale/offset.
"""
from .automap import solve as automap_solve
from .calib import solve_linear, suggest_signal
from .decoder import LidStore, parse_hex_line

__all__ = ["LidStore", "parse_hex_line", "solve_linear", "suggest_signal", "automap_solve"]
