"""Td5 fault codes: decoding of the status block from ReadDataByLocalIdentifier 0x3B.

The block (bytes after ``61 3B``) is bit-coded — each bit corresponds to a fault.
Fault index = offset*8 + bit (bit 0 = mask 0x01). The map is PROVEN from Ekaitza_Itzali
(get_faults + fault_code_text) and **cross-validated against reference tool v1.12** — both
sources give the same name for the same offset/bit. It is protocol fact about the ECU's
diagnostics, no code copied — see THIRD_PARTY_LICENSES.md. Obvious source typos
corrected (peck→peak, crack→crank, inlett→inlet).

Status suffix (from the reference tool distinction, more precise than Ekaitza's coarse L/C):
**(Logged Low)** = stored, signal low (short circuit/low voltage) — offset 0–1 for
the sensor circuits; **(Logged High)** = stored, signal high (open circuit) — offset 2–3;
**(Current)** = fault present right now; **(Logged)** = stored historically (drive
stages etc., where Low/High does not apply). Unknown set bits are reported generically so
nothing is dropped silently (the name table lacks text for some bits — undefined in the source).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    offset: int  # byte offset in the block (0 = first byte after 61 3B)
    mask: int    # bitmask within that byte (bit 0 = 0x01 … bit 7 = 0x80)
    name: str


# The status block is 35 bytes (offset 0–34). The tolerant read may drag along
# the frame's checksum/glitch after the block — those must NOT be decoded as faults.
FAULT_BLOCK_LEN = 35

# Fault map from Ekaitza + reference tool v1.12 (210 named bits, offset 0–34). PROVEN.
FAULTS: "list[Fault]" = [
    Fault(0, 0x01, "egr inlet throttle diagnostics (Logged Low)"),
    Fault(0, 0x02, "turbocharger wastegate diagnostics (Logged Low)"),
    Fault(0, 0x04, "egr vacuum diagnostics (Logged Low)"),
    Fault(0, 0x08, "temperature gauge diagnostics (Logged Low)"),
    Fault(0, 0x10, "driver demand problem 1 (Logged Low)"),
    Fault(0, 0x20, "driver demand problem 2 (Logged Low)"),
    Fault(0, 0x40, "air flow circuit (Logged Low)"),
    Fault(0, 0x80, "manifold pressure circuit (Logged Low)"),
    Fault(1, 0x01, "inlet air temp. circuit (Logged Low)"),
    Fault(1, 0x02, "fuel temp. circuit (Logged Low)"),
    Fault(1, 0x04, "coolant temp. circuit (Logged Low)"),
    Fault(1, 0x08, "battery volts (Logged Low)"),
    Fault(1, 0x10, "reference voltage (Logged Low)"),
    Fault(1, 0x20, "ambient air temp. circuit (Logged Low)"),
    Fault(1, 0x40, "driver demand supply problem (Logged Low)"),
    Fault(1, 0x80, "ambient pressure circuit (Logged Low)"),
    Fault(2, 0x01, "egr inlet throttle diagnostics (Logged High)"),
    Fault(2, 0x02, "turbocharger wastegate diagnostics (Logged High)"),
    Fault(2, 0x04, "egr vacuum diagnostics (Logged High)"),
    Fault(2, 0x08, "temperature gauge diagnostics (Logged High)"),
    Fault(2, 0x10, "driver demand problem 1 (Logged High)"),
    Fault(2, 0x20, "driver demand problem 2 (Logged High)"),
    Fault(2, 0x40, "air flow circuit (Logged High)"),
    Fault(2, 0x80, "manifold pressure circuit (Logged High)"),
    Fault(3, 0x01, "inlet air temp. circuit (Logged High)"),
    Fault(3, 0x02, "fuel temperature circuit (Logged High)"),
    Fault(3, 0x04, "coolant temp. circuit (Logged High)"),
    Fault(3, 0x08, "battery volts (Logged High)"),
    Fault(3, 0x10, "reference voltage (Logged High)"),
    Fault(3, 0x20, "ambient air temperature circuit (Logged High)"),
    Fault(3, 0x40, "driver demand supply problem (Logged High)"),
    Fault(3, 0x80, "ambient pressure circuit (Logged High)"),
    Fault(4, 0x01, "egr inlet throttle diagnostics (Current)"),
    Fault(4, 0x02, "turbocharger wastegate diagnostics (Current)"),
    Fault(4, 0x04, "egr vacuum diagnostics (Current)"),
    Fault(4, 0x08, "temperature gauge diagnostics (Current)"),
    Fault(4, 0x10, "driver demand problem 1 (Current)"),
    Fault(4, 0x20, "driver demand problem 2 (Current)"),
    Fault(4, 0x40, "air flow circuit (Current)"),
    Fault(4, 0x80, "manifold pressure circuit (Current)"),
    Fault(5, 0x01, "inlet air temp. circuit (Current)"),
    Fault(5, 0x02, "fuel temperature circuit (Current)"),
    Fault(5, 0x04, "coolant temp. circuit (Current)"),
    Fault(5, 0x08, "battery voltage problem (Current)"),
    Fault(5, 0x10, "reference voltage (Current)"),
    Fault(5, 0x40, "driver demand supply problem (Current)"),
    Fault(5, 0x80, "ambient pressure circuit (Current)"),
    Fault(6, 0x01, "cruise lamp drive over temp. (Logged)"),
    Fault(6, 0x02, "fuel used output drive over temp. (Logged)"),
    Fault(6, 0x04, "radiator fan drive over temp. (Logged)"),
    Fault(6, 0x08, "active engine mounting over temp. (Logged)"),
    Fault(6, 0x10, "turbocharger wastegate short circuit (Logged)"),
    Fault(6, 0x20, "egr inlet throttle short circuit (Logged)"),
    Fault(6, 0x40, "egr vacuum modulator short circuit (Logged)"),
    Fault(6, 0x80, "temperature gauge short circuit (Logged)"),
    Fault(7, 0x01, "air conditioning fan drive over temp. (Logged)"),
    Fault(7, 0x02, "fuel pump drive over temp. (Logged)"),
    Fault(7, 0x04, "tacho drive over temp. (Logged)"),
    Fault(7, 0x08, "gearbox/abs drive over temp. (Logged)"),
    Fault(7, 0x10, "air conditioning clutch over temp. (Logged)"),
    Fault(7, 0x20, "mil lamp drive over temp. (Logged)"),
    Fault(7, 0x40, "glow plug relay drive over temp. (Logged)"),
    Fault(7, 0x80, "glowplug lamp drive over temperature (Logged)"),
    Fault(8, 0x01, "fuel used output drive open load (Logged)"),
    Fault(8, 0x02, "cruise lamp drive open load (Logged)"),
    Fault(8, 0x04, "radiator fan drive open load (Logged)"),
    Fault(8, 0x08, "active engine mounting open load (Logged)"),
    Fault(8, 0x10, "turbocharger wastegate open load (Logged)"),
    Fault(8, 0x20, "egr inlet throttle open load (Logged)"),
    Fault(8, 0x40, "egr vacuum modulator open load (Logged)"),
    Fault(8, 0x80, "temperature gauge open load (Logged)"),
    Fault(9, 0x01, "air conditioning fan drive open load (Logged)"),
    Fault(9, 0x02, "fuel pump drive open load (Logged)"),
    Fault(9, 0x04, "tachometer open load (Logged)"),
    Fault(9, 0x08, "gearbox/abs drive open load (Logged)"),
    Fault(9, 0x10, "air conditioning clutch open load (Logged)"),
    Fault(9, 0x20, "mil lamp drive open load (Logged)"),
    Fault(9, 0x40, "glow plug lamp drive open load (Logged)"),
    Fault(9, 0x80, "glow plug relay drive open load (Logged)"),
    Fault(10, 0x01, "cruise control lamp drive over temperature (Current)"),
    Fault(10, 0x02, "fuel used output drive over temperature (Current)"),
    Fault(10, 0x04, "radiator fan drive over temperature (Current)"),
    Fault(10, 0x08, "active engine mounting over temperature (Current)"),
    Fault(10, 0x10, "turbocharger wastegate short circuit (Current)"),
    Fault(10, 0x20, "egr inlet throttle short circuit (Current)"),
    Fault(10, 0x40, "egr vacuum modulator short circuit (Current)"),
    Fault(10, 0x80, "temperature gauge short circuit (Current)"),
    Fault(11, 0x01, "air conditioning fan drive open load (Current)"),
    Fault(11, 0x02, "fuel pump drive open load (Current)"),
    Fault(11, 0x04, "tachometer open load (Current)"),
    Fault(11, 0x08, "gearbox/abs drive open load (Current)"),
    Fault(11, 0x10, "air conditioning clutch open load (Current)"),
    Fault(11, 0x20, "mil lamp drive open load (Current)"),
    Fault(11, 0x40, "glow plug relay drive open load (Current)"),
    Fault(11, 0x80, "glowplug relay drive open load (Current)"),
    Fault(12, 0x01, "cruise control lamp drive over temp. (Current)"),
    Fault(12, 0x02, "fuel used output drive over temp. (Current)"),
    Fault(12, 0x04, "radiator fan drive over temp. (Current)"),
    Fault(12, 0x08, "active engine mounting over temp. (Current)"),
    Fault(12, 0x10, "turbocharger wastegate short circuit (Current)"),
    Fault(12, 0x20, "egr inlet throttle short circuit (Current)"),
    Fault(12, 0x40, "egr vacuum modulator short circuit (Current)"),
    Fault(12, 0x80, "temperature gauge short circuit (Current)"),
    Fault(13, 0x01, "air conditioning fan drive open load (Current)"),
    Fault(13, 0x02, "fuel pump drive open load (Current)"),
    Fault(13, 0x04, "tachometer open load (Current)"),
    Fault(13, 0x08, "gearbox/abs drive open load (Current)"),
    Fault(13, 0x10, "air conditioning clutch open load (Current)"),
    Fault(13, 0x20, "mil lamp drive open load (Current)"),
    Fault(13, 0x40, "glow plug relay drive open load (Current)"),
    Fault(13, 0x80, "glowplug relay drive open load (Current)"),
    Fault(14, 0x02, "high speed crank (Logged)"),
    Fault(15, 0x02, "high speed crank (Logged)"),
    Fault(16, 0x02, "high speed crank (Current)"),
    Fault(18, 0x02, "can rx/tx error (Logged)"),
    Fault(18, 0x04, "can tx/rx error (Logged)"),
    Fault(18, 0x20, "noisy crank signal has been detected (Logged)"),
    Fault(18, 0x80, "can has had reset failure (Logged)"),
    Fault(19, 0x01, "turbocharger under boosting (Logged)"),
    Fault(19, 0x02, "turbocharger over boosting (Logged)"),
    Fault(19, 0x08, "egr valve stuck open (Logged)"),
    Fault(19, 0x10, "egr valve stuck closed (Logged)"),
    Fault(20, 0x08, "driver demand 1 out of range (Logged)"),
    Fault(20, 0x10, "driver demand 2 out of range (Logged)"),
    Fault(20, 0x20, "problem detected with driver demand (Logged)"),
    Fault(20, 0x40, "inconsistencies found with driver demand (Logged)"),
    Fault(21, 0x01, "road speed missing (Logged)"),
    Fault(21, 0x04, "vehicle accel. outside bounds of cruise control (Logged)"),
    Fault(21, 0x40, "cruise control resume stuck closed (Logged)"),
    Fault(21, 0x80, "cruise control set stuck closed (Logged)"),
    Fault(22, 0x01, "excessive can bus off (Current)"),
    Fault(22, 0x02, "can rx/tx error (Current)"),
    Fault(22, 0x04, "can tx/rx error (Current)"),
    Fault(22, 0x08, "unable to detect remote can mode (Current)"),
    Fault(22, 0x10, "under boost has occurred on this trip (Current)"),
    Fault(22, 0x20, "noisy crank signal has been detected (Current)"),
    Fault(23, 0x01, "turbocharger under boosting (Current)"),
    Fault(23, 0x02, "turbocharger over boosting (Current)"),
    Fault(23, 0x04, "over boost has occurred this trip (Current)"),
    Fault(23, 0x08, "egr valve stuck open (Current)"),
    Fault(23, 0x10, "egr valve stuck closed (Current)"),
    Fault(23, 0x40, "problem detected with auto gear box (Current)"),
    Fault(24, 0x08, "driver demand 1 out of range (Logged)"),
    Fault(24, 0x10, "driver demand 2 out of range (Logged)"),
    Fault(24, 0x20, "problem detected with drive demand (Current)"),
    Fault(24, 0x40, "inconsistencies found with driver demand (Current)"),
    Fault(24, 0x80, "injector trim data corrupted (Current)"),
    Fault(25, 0x01, "road speed missing (Current)"),
    Fault(25, 0x02, "cruise control system problem (Current)"),
    Fault(25, 0x04, "vehicle accel. outside bounds for cruise control (Current)"),
    Fault(25, 0x40, "cruise control resume stuck closed (Current)"),
    Fault(25, 0x80, "cruise control set stuck closed (Current)"),
    Fault(26, 0x01, "inj. 1 peak charge long (Logged)"),
    Fault(26, 0x02, "inj. 2 peak charge long (Logged)"),
    Fault(26, 0x04, "inj. 3 peak charge long (Logged)"),
    Fault(26, 0x08, "inj. 4 peak charge long (Logged)"),
    Fault(26, 0x10, "inj. 5 peak charge long (Logged)"),
    Fault(26, 0x20, "inj. 6 peak charge long (Logged)"),
    Fault(26, 0x40, "topside switch failed post injection (Logged)"),
    Fault(27, 0x01, "inj. 1 peak charge short (Logged)"),
    Fault(27, 0x02, "inj. 2 peak charge short (Logged)"),
    Fault(27, 0x04, "inj. 3 peak charge short (Logged)"),
    Fault(27, 0x08, "inj. 4 peak charge short (Logged)"),
    Fault(27, 0x10, "inj. 5 peak charge short (Logged)"),
    Fault(27, 0x20, "inj. 6 peak charge short (Logged)"),
    Fault(27, 0x40, "topside switch failed pre injection (Logged)"),
    Fault(28, 0x01, "inj. 1 peak charge long (Current)"),
    Fault(28, 0x02, "inj. 2 peak charge long (Current)"),
    Fault(28, 0x04, "inj. 3 peak charge long (Current)"),
    Fault(28, 0x08, "inj. 4 peak charge long (Current)"),
    Fault(28, 0x10, "inj. 5 peak charge long (Current)"),
    Fault(28, 0x20, "inj. 6 peak charge long (Current)"),
    Fault(28, 0x40, "topside switch failed post injection (Current)"),
    Fault(29, 0x01, "inj. 1 peak charge short (Current)"),
    Fault(29, 0x02, "inj. 2 peak charge short (Current)"),
    Fault(29, 0x04, "inj. 3 peak charge short (Current)"),
    Fault(29, 0x08, "inj. 4 peak charge short (Current)"),
    Fault(29, 0x10, "inj. 5 peak charge short (Current)"),
    Fault(29, 0x20, "inj. 6 peak charge short (Current)"),
    Fault(29, 0x40, "topside switch failed pre injection (Current)"),
    Fault(30, 0x01, "inj. 1 open circuit (Logged)"),
    Fault(30, 0x02, "inj. 2 open circuit (Logged)"),
    Fault(30, 0x04, "inj. 3 open circuit (Logged)"),
    Fault(30, 0x08, "inj. 4 open circuit (Logged)"),
    Fault(30, 0x10, "inj. 5 open circuit (Logged)"),
    Fault(30, 0x20, "inj. 6 open circuit (Logged)"),
    Fault(31, 0x01, "inj. 1 short circuit (Logged)"),
    Fault(31, 0x02, "inj. 2 short circuit (Logged)"),
    Fault(31, 0x04, "inj. 3 short circuit (Logged)"),
    Fault(31, 0x08, "inj. 4 short circuit (Logged)"),
    Fault(31, 0x10, "inj. 5 short circuit (Logged)"),
    Fault(31, 0x20, "inj. 6 short circuit (Logged)"),
    Fault(32, 0x01, "inj. 1 open circuit (Current)"),
    Fault(32, 0x02, "inj. 2 open circuit (Current)"),
    Fault(32, 0x04, "inj. 3 open circuit (Current)"),
    Fault(32, 0x08, "inj. 4 open circuit (Current)"),
    Fault(32, 0x10, "inj. 5 open circuit (Current)"),
    Fault(32, 0x20, "inj. 6 open circuit (Current)"),
    Fault(33, 0x01, "inj. 1 short circuit (Current)"),
    Fault(33, 0x02, "inj. 2 short circuit (Current)"),
    Fault(33, 0x04, "inj. 3 short circuit (Current)"),
    Fault(33, 0x08, "inj. 4 short circuit (Current)"),
    Fault(33, 0x10, "inj. 5 short circuit (Current)"),
    Fault(33, 0x20, "inj. 6 short circuit (Current)"),
    Fault(34, 0x01, "inj. 1 partial short circuit (Logged)"),
    Fault(34, 0x02, "inj. 2 partial short circuit (Logged)"),
    Fault(34, 0x04, "inj. 3 partial short circuit (Logged)"),
    Fault(34, 0x08, "inj. 4 partial short circuit (Logged)"),
    Fault(34, 0x10, "inj. 5 partial short circuit (Logged)"),
    Fault(34, 0x20, "inj. 6 partial short circuit (Logged)"),
]


def decode_faults(block: bytes) -> "list[str]":
    """Return a list of active faults from the status block.

    Known bits (in :data:`FAULTS`) are given their name. Set bits without a known
    mapping are reported generically as ``byte<off>.bit<n>`` so an unknown fault bit
    never disappears silently.
    """
    block = block[:FAULT_BLOCK_LEN]  # trim off any checksum/glitch after the block
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
