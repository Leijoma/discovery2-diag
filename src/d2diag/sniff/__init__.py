"""Passiv sniff-kalibrering — läs reference tool-trafik (RX-only) och mappa LID-fält.

Eftersom vår ESP32-tapp aldrig sänder måste reference tool vara inkopplad och polla;
vi avkodar passivt och jämför mot reference tools skärm för att lösa skala/offset.
"""
from .automap import solve as automap_solve
from .calib import solve_linear, suggest_signal
from .decoder import LidStore, parse_hex_line

__all__ = ["LidStore", "parse_hex_line", "solve_linear", "suggest_signal", "automap_solve"]
