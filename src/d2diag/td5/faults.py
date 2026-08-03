"""Td5-felkoder: avkodning av statusblocket från ReadDataByLocalIdentifier 0x3B.

Blocket (bytes efter ``61 3B``) är bitkodat — varje bit motsvarar ett fel.
Felindex = offset*8 + bit (bit 0 = mask 0x01). Kartan är BELAGD ur Ekaitza_Itzali
(get_faults + fault_code_text); det är protokollfakta om ECU:ns diagnostik, ingen
kod kopierad — se THIRD_PARTY_LICENSES.md. Uppenbara källstavfel rättade
(peck→peak, crack→crank, inlett→inlet).

Suffix: **(L)** = Logged/lagrat (historiskt fel), **(C)** = Current/aktuellt fel.
Okända satta bitar rapporteras generiskt så inget tappas tyst innan kartan är
komplett (namntabellen saknar text för vissa bitar — de är odefinierade i källan).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    offset: int  # byte-offset i blocket (0 = första byten efter 61 3B)
    mask: int    # bitmask i den byten (bit 0 = 0x01 … bit 7 = 0x80)
    name: str


# Statusblocket är 35 bytes (offset 0–34). Den toleranta läsningen kan släpa med
# ramens checksumma/glitch efter blocket — de ska INTE avkodas som fel.
FAULT_BLOCK_LEN = 35

# Felkarta ur Ekaitza (210 namngivna bitar, offset 0–34). BELAGD.
FAULTS: "list[Fault]" = [
    Fault(0, 0x01, "egr inlet throttle diagnostics (L)"),
    Fault(0, 0x02, "turbocharger wastegate diagnostics (L)"),
    Fault(0, 0x04, "egr vacuum diagnostics (L)"),
    Fault(0, 0x08, "temperature gauge diagnostics (L)"),
    Fault(0, 0x10, "driver demand problem 1 (L)"),
    Fault(0, 0x20, "driver demand problem 2 (L)"),
    Fault(0, 0x40, "air flow circuit (L)"),
    Fault(0, 0x80, "manifold pressure circuit (L)"),
    Fault(1, 0x01, "inlet air temp. circuit (L)"),
    Fault(1, 0x02, "fuel temp. circuit (L)"),
    Fault(1, 0x04, "coolant temp. circuit (L)"),
    Fault(1, 0x08, "battery volts (L)"),
    Fault(1, 0x10, "reference voltage (L)"),
    Fault(1, 0x20, "ambient air temp. circuit (L)"),
    Fault(1, 0x40, "driver demand supply problem (L)"),
    Fault(1, 0x80, "ambient pressure circuit (L)"),
    Fault(2, 0x01, "egr inlet throttle diagnostics (L)"),
    Fault(2, 0x02, "turbocharger wastegate diagnostics (L)"),
    Fault(2, 0x04, "egr vacuum diagnostics (L)"),
    Fault(2, 0x08, "temperature gauge diagnostics (L)"),
    Fault(2, 0x10, "driver demand problem 1 (L)"),
    Fault(2, 0x20, "driver demand problem 2 (L)"),
    Fault(2, 0x40, "air flow circuit (L)"),
    Fault(2, 0x80, "manifold pressure circuit (L)"),
    Fault(3, 0x01, "inlet air temp. circuit (L)"),
    Fault(3, 0x02, "fuel temperature circuit (L)"),
    Fault(3, 0x04, "coolant temp. circuit (L)"),
    Fault(3, 0x08, "battery volts (L)"),
    Fault(3, 0x10, "reference voltage (L)"),
    Fault(3, 0x20, "ambient air temperature circuit (L)"),
    Fault(3, 0x40, "driver demand supply problem (L)"),
    Fault(3, 0x80, "ambient pressure circuit (L)"),
    Fault(4, 0x01, "egr inlet throttle diagnostics (C)"),
    Fault(4, 0x02, "turbocharger wastegate diagnostics (C)"),
    Fault(4, 0x04, "egr vacuum diagnostics (C)"),
    Fault(4, 0x08, "temperature gauge diagnostics (C)"),
    Fault(4, 0x10, "driver demand problem 1 (C)"),
    Fault(4, 0x20, "driver demand problem 2 (C)"),
    Fault(4, 0x40, "air flow circuit (C)"),
    Fault(4, 0x80, "manifold pressure circuit (C)"),
    Fault(5, 0x01, "inlet air temp. circuit (C)"),
    Fault(5, 0x02, "fuel temperature circuit (C)"),
    Fault(5, 0x04, "coolant temp. circuit (C)"),
    Fault(5, 0x08, "battery voltage problem (C)"),
    Fault(5, 0x10, "reference voltage (C)"),
    Fault(5, 0x40, "driver demand supply problem (C)"),
    Fault(5, 0x80, "ambient pressure circuit (C)"),
    Fault(6, 0x01, "cruise lamp drive over temp. (L)"),
    Fault(6, 0x02, "fuel used output drive over temp. (L)"),
    Fault(6, 0x04, "radiator fan drive over temp. (L)"),
    Fault(6, 0x08, "active engine mounting over temp. (L)"),
    Fault(6, 0x10, "turbocharger wastegate short circuit (L)"),
    Fault(6, 0x20, "egr inlet throttle short circuit (L)"),
    Fault(6, 0x40, "egr vacuum modulator short circuit (L)"),
    Fault(6, 0x80, "temperature gauge short circuit (L)"),
    Fault(7, 0x01, "air conditioning fan drive over temp. (L)"),
    Fault(7, 0x02, "fuel pump drive over temp. (L)"),
    Fault(7, 0x04, "tacho drive over temp. (L)"),
    Fault(7, 0x08, "gearbox/abs drive over temp. (L)"),
    Fault(7, 0x10, "air conditioning clutch over temp. (L)"),
    Fault(7, 0x20, "mil lamp drive over temp. (L)"),
    Fault(7, 0x40, "glow plug relay drive over temp. (L)"),
    Fault(7, 0x80, "glowplug lamp drive over temperature (L)"),
    Fault(8, 0x01, "fuel used output drive open load (L)"),
    Fault(8, 0x02, "cruise lamp drive open load (L)"),
    Fault(8, 0x04, "radiator fan drive open load (L)"),
    Fault(8, 0x08, "active engine mounting open load (L)"),
    Fault(8, 0x10, "turbocharger wastegate open load (L)"),
    Fault(8, 0x20, "egr inlet throttle open load (L)"),
    Fault(8, 0x40, "egr vacuum modulator open load (L)"),
    Fault(8, 0x80, "temperature gauge open load (L)"),
    Fault(9, 0x01, "air conditioning fan drive open load (L)"),
    Fault(9, 0x02, "fuel pump drive open load (L)"),
    Fault(9, 0x04, "tachometer open load (L)"),
    Fault(9, 0x08, "gearbox/abs drive open load (L)"),
    Fault(9, 0x10, "air conditioning clutch open load (L)"),
    Fault(9, 0x20, "mil lamp drive open load (L)"),
    Fault(9, 0x40, "glow plug lamp drive open load (L)"),
    Fault(9, 0x80, "glow plug relay drive open load (L)"),
    Fault(10, 0x01, "cruise control lamp drive over temperature (C)"),
    Fault(10, 0x02, "fuel used output drive over temperature (C)"),
    Fault(10, 0x04, "radiator fan drive over temperature (C)"),
    Fault(10, 0x08, "active engine mounting over temperature (C)"),
    Fault(10, 0x10, "turbocharger wastegate short circuit (C)"),
    Fault(10, 0x20, "egr inlet throttle short circuit (C)"),
    Fault(10, 0x40, "egr vacuum modulator short circuit (C)"),
    Fault(10, 0x80, "temperature gauge short circuit (C)"),
    Fault(11, 0x01, "air conditioning fan drive open load (C)"),
    Fault(11, 0x02, "fuel pump drive open load (C)"),
    Fault(11, 0x04, "tachometer open load (C)"),
    Fault(11, 0x08, "gearbox/abs drive open load (C)"),
    Fault(11, 0x10, "air conditioning clutch open load (C)"),
    Fault(11, 0x20, "mil lamp drive open load (C)"),
    Fault(11, 0x40, "glow plug relay drive open load (C)"),
    Fault(11, 0x80, "glowplug relay drive open load (C)"),
    Fault(12, 0x01, "cruise control lamp drive over temp. (C)"),
    Fault(12, 0x02, "fuel used output drive over temp. (C)"),
    Fault(12, 0x04, "radiator fan drive over temp. (C)"),
    Fault(12, 0x08, "active engine mounting over temp. (C)"),
    Fault(12, 0x10, "turbocharger wastegate short circuit (C)"),
    Fault(12, 0x20, "egr inlet throttle short circuit (C)"),
    Fault(12, 0x40, "egr vacuum modulator short circuit (C)"),
    Fault(12, 0x80, "temperature gauge short circuit (C)"),
    Fault(13, 0x01, "air conditioning fan drive open load (C)"),
    Fault(13, 0x02, "fuel pump drive open load (C)"),
    Fault(13, 0x04, "tachometer open load (C)"),
    Fault(13, 0x08, "gearbox/abs drive open load (C)"),
    Fault(13, 0x10, "air conditioning clutch open load (C)"),
    Fault(13, 0x20, "mil lamp drive open load (C)"),
    Fault(13, 0x40, "glow plug relay drive open load (C)"),
    Fault(13, 0x80, "glowplug relay drive open load (C)"),
    Fault(14, 0x02, "high speed crank (L)"),
    Fault(15, 0x02, "high speed crank (L)"),
    Fault(16, 0x02, "high speed crank (C)"),
    Fault(18, 0x02, "can rx/tx error (L)"),
    Fault(18, 0x04, "can tx/rx error (L)"),
    Fault(18, 0x20, "noisy crank signal has been detected (L)"),
    Fault(18, 0x80, "can has had reset failure (L)"),
    Fault(19, 0x01, "turbocharger under boosting (L)"),
    Fault(19, 0x02, "turbocharger over boosting (L)"),
    Fault(19, 0x08, "egr valve stuck open (L)"),
    Fault(19, 0x10, "egr valve stuck closed (L)"),
    Fault(20, 0x08, "driver demand 1 out of range (L)"),
    Fault(20, 0x10, "driver demand 2 out of range (L)"),
    Fault(20, 0x20, "problem detected with driver demand (L)"),
    Fault(20, 0x40, "inconsistencies found with driver demand (L)"),
    Fault(21, 0x01, "road speed missing (L)"),
    Fault(21, 0x04, "vehicle accel. outside bounds of cruise control (L)"),
    Fault(21, 0x40, "cruise control resume stuck closed (L)"),
    Fault(21, 0x80, "cruise control set stuck closed (L)"),
    Fault(22, 0x01, "excessive can bus off (C)"),
    Fault(22, 0x02, "can rx/tx error (C)"),
    Fault(22, 0x04, "can tx/rx error (C)"),
    Fault(22, 0x08, "unable to detect remote can mode (C)"),
    Fault(22, 0x10, "under boost has occurred on this trip (C)"),
    Fault(22, 0x20, "noisy crank signal has been detected (C)"),
    Fault(23, 0x01, "turbocharger under boosting (C)"),
    Fault(23, 0x02, "turbocharger over boosting (C)"),
    Fault(23, 0x04, "over boost has occurred this trip (C)"),
    Fault(23, 0x08, "egr valve stuck open (C)"),
    Fault(23, 0x10, "egr valve stuck closed (C)"),
    Fault(23, 0x40, "problem detected with auto gear box (C)"),
    Fault(24, 0x08, "driver demand 1 out of range (L)"),
    Fault(24, 0x10, "driver demand 2 out of range (L)"),
    Fault(24, 0x20, "problem detected with drive demand (C)"),
    Fault(24, 0x40, "inconsistencies found with driver demand (C)"),
    Fault(24, 0x80, "injector trim data corrupted (C)"),
    Fault(25, 0x01, "road speed missing (C)"),
    Fault(25, 0x02, "cruise control system problem (C)"),
    Fault(25, 0x04, "vehicle accel. outside bounds for cruise control (C)"),
    Fault(25, 0x40, "cruise control resume stuck closed (C)"),
    Fault(25, 0x80, "cruise control set stuck closed (C)"),
    Fault(26, 0x01, "inj. 1 peak charge long (L)"),
    Fault(26, 0x02, "inj. 2 peak charge long (L)"),
    Fault(26, 0x04, "inj. 3 peak charge long (L)"),
    Fault(26, 0x08, "inj. 4 peak charge long (L)"),
    Fault(26, 0x10, "inj. 5 peak charge long (L)"),
    Fault(26, 0x20, "inj. 6 peak charge long (L)"),
    Fault(26, 0x40, "topside switch failed post injection (L)"),
    Fault(27, 0x01, "inj. 1 peak charge short (L)"),
    Fault(27, 0x02, "inj. 2 peak charge short (L)"),
    Fault(27, 0x04, "inj. 3 peak charge short (L)"),
    Fault(27, 0x08, "inj. 4 peak charge short (L)"),
    Fault(27, 0x10, "inj. 5 peak charge short (L)"),
    Fault(27, 0x20, "inj. 6 peak charge short (L)"),
    Fault(27, 0x40, "topside switch failed pre injection (L)"),
    Fault(28, 0x01, "inj. 1 peak charge long (C)"),
    Fault(28, 0x02, "inj. 2 peak charge long (C)"),
    Fault(28, 0x04, "inj. 3 peak charge long (C)"),
    Fault(28, 0x08, "inj. 4 peak charge long (C)"),
    Fault(28, 0x10, "inj. 5 peak charge long (C)"),
    Fault(28, 0x20, "inj. 6 peak charge long (C)"),
    Fault(28, 0x40, "topside switch failed post injection (C)"),
    Fault(29, 0x01, "inj. 1 peak charge short (C)"),
    Fault(29, 0x02, "inj. 2 peak charge short (C)"),
    Fault(29, 0x04, "inj. 3 peak charge short (C)"),
    Fault(29, 0x08, "inj. 4 peak charge short (C)"),
    Fault(29, 0x10, "inj. 5 peak charge short (C)"),
    Fault(29, 0x20, "inj. 6 peak charge short (C)"),
    Fault(29, 0x40, "topside switch failed pre injection (C)"),
    Fault(30, 0x01, "inj. 1 open circuit (L)"),
    Fault(30, 0x02, "inj. 2 open circuit (L)"),
    Fault(30, 0x04, "inj. 3 open circuit (L)"),
    Fault(30, 0x08, "inj. 4 open circuit (L)"),
    Fault(30, 0x10, "inj. 5 open circuit (L)"),
    Fault(30, 0x20, "inj. 6 open circuit (L)"),
    Fault(31, 0x01, "inj. 1 short circuit (L)"),
    Fault(31, 0x02, "inj. 2 short circuit (L)"),
    Fault(31, 0x04, "inj. 3 short circuit (L)"),
    Fault(31, 0x08, "inj. 4 short circuit (L)"),
    Fault(31, 0x10, "inj. 5 short circuit (L)"),
    Fault(31, 0x20, "inj. 6 short circuit (L)"),
    Fault(32, 0x01, "inj. 1 open circuit (C)"),
    Fault(32, 0x02, "inj. 2 open circuit (C)"),
    Fault(32, 0x04, "inj. 3 open circuit (C)"),
    Fault(32, 0x08, "inj. 4 open circuit (C)"),
    Fault(32, 0x10, "inj. 5 open circuit (C)"),
    Fault(32, 0x20, "inj. 6 open circuit (C)"),
    Fault(33, 0x01, "inj. 1 short circuit (C)"),
    Fault(33, 0x02, "inj. 2 short circuit (C)"),
    Fault(33, 0x04, "inj. 3 short circuit (C)"),
    Fault(33, 0x08, "inj. 4 short circuit (C)"),
    Fault(33, 0x10, "inj. 5 short circuit (C)"),
    Fault(33, 0x20, "inj. 6 short circuit (C)"),
    Fault(34, 0x01, "inj. 1 partial short circuit (L)"),
    Fault(34, 0x02, "inj. 2 partial short circuit (L)"),
    Fault(34, 0x04, "inj. 3 partial short circuit (L)"),
    Fault(34, 0x08, "inj. 4 partial short circuit (L)"),
    Fault(34, 0x10, "inj. 5 partial short circuit (L)"),
    Fault(34, 0x20, "inj. 6 partial short circuit (L)"),
]


def decode_faults(block: bytes) -> "list[str]":
    """Returnera en lista med aktiva fel ur statusblocket.

    Kända bitar (i :data:`FAULTS`) ges sitt namn. Satta bitar utan känd mappning
    rapporteras generiskt som ``byte<off>.bit<n>`` så att en okänd felbit aldrig
    försvinner tyst.
    """
    block = block[:FAULT_BLOCK_LEN]  # kapa bort ev. checksumma/glitch efter blocket
    active: "list[str]" = []
    known_mask: "dict[int, int]" = {}
    for f in FAULTS:
        known_mask[f.offset] = known_mask.get(f.offset, 0) | (f.mask & 0xFF)
        if f.offset < len(block) and (block[f.offset] & f.mask):
            active.append(f.name)
    for off, byte in enumerate(block):
        unknown = byte & ~known_mask.get(off, 0) & 0xFF
        for bit in range(8):
            if unknown & (1 << bit):
                active.append(f"byte{off}.bit{bit}")
    return active
