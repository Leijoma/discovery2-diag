# reference tool menu map (RDL 016) + cross-reference against sniffed protocol

Source: the owner's `Discovery 2/reference tool.txt` — the menus in the borrowed reference tool (reference tool 1).
This is the **index** for decoding which `21 xx` LIDs / `31 xx` routines are what.

## Modules (this car's reference tool)
TD5 · Motronic (*V8, requires unlock — not this car*) · **SLABS** · **VALEO BCU** ·
**ACE** · **D2 AUTOGEARBOX** · **Airbag**

**Shared submenu per module:** Faults (read/clear) · Settings (read/write) ·
Inputs · Outputs (valves/lamps on/off) · Utility (module-specific).
⇒ Same structure to sniff for BCU/ACE/gearbox/airbag.

## SLABS — inputs (reference tool order) ↔ our LIDs
Settings (confirmed sniffed): test status en/dis · ecu calibrated · transport mode ·
suspension type AIR/springs.

**Inputs list** (reference tool): ABS sensor FR/FL/RR/RL · wheel speed FR/FL/RR/RL ·
inlet valve ×4 · outlet valve ×4 · pump monitor (V) · pump relay (V) · Battery (V) ·
ECU internal supply (V) · Ground Reference (V) · Engine speed (rpm) · Engine Torque ·
Throttle % · HDC Brake (V) · Shuttle Switch · Left/Right Sensor Value · Left/Right
Sensor Supply (V) · Left/Right Value (V) · Exhaust Valve (V) · Compressor Relay (V) ·
Neutral/Low Range/Diff Lock/Reverse/HDC/Any Door Switch · Plip signal.

**Cross-reference against captured `21 xx`** (proven / likely / to be confirmed):
| LID | Captured bytes | Likely interpretation |
|---|---|---|
| `21 54` | `91 9c 0f 0f` | ✅ **Left/Right Sensor Value** (heights): b0=145≈left, b1=156≈right (matches baseline L143/R157) |
| `21 50` | `72 73 73 72` | ✅ **ABS sensor FR/FL/RR/RL** (V): 0x72≈114 → ~2.28 V (spec 2.0–2.4 V) |
| `21 43` | `7c 00 7c 00 7c 00 7c 00` | **wheel speed FR/FL/RR/RL** (0 stationary) |
| `21 44` | `00 80 01 02 01 01 02 01 02 02 03 04 …` | inlet/outlet valve voltages (8 of them)? to be confirmed |
| `21 53` | `d2 d2 0f 0f` | Left/Right Sensor Supply or Value (V)? to be confirmed |
| `21 42/48/56/58` | `82` / `94 61` / … | switch block (Neutral/Diff/HDC/Shuttle…)? to be confirmed |
| `21 11` | 16-byte bitfield | ✅ **logged faults** · `21 47` = current |
Others (`21 45/46/49/55/57/59`) = further input fields — mapped when we read in menu order.

## SLABS — Outputs (on/off) — reference tool order
FR/FL/RR/RL **Inlet/Outlet Valve** (8) · SLS **Left/Right/Exhaust valve** · **ABS Pump
relay** · **Speedometer** · **SLS Compressor** · **SLS Buzzer** · **T.C. Lamp** · **ABS
Warning Light** · **HDC Warning Light** · **Brake Warning Light** · **SLS lamps** ·
**Offroad Lamp** · **HDC Fault lamps** · **HDC Brake lamps**.

**Proven (sniffed) `31 xx` routines:** exhaust=`2F` · compressor=`30` · buzzer=`31` ·
pump relay=`25` · wheel-valve test=`22 <sub>`. **The lamps (T.C./ABS/HDC/Brake/SLS/
Offroad) = were NOT captured cleanly** (first log was garbage) → **re-log Outputs in the
list order above** so each lamp maps → `31 xx`.

## SLABS — Utility
ABS Bleeding tests · **Power Bleed** (`31 22 04 …`) · **Modulator Bleed**
(`31 22 11/12/13/14 …`) · **FR/FL/RR/RL Test** (`31 22 <sub> <mask> c1 f4`, mask =
wheel bitmask) · **SLS height calibration** · **Raise/Lower Left/Right** (`31 33-36`) ·
**Store heights** (⚠️ writes calibration — do not touch).

## Next
Re-log **Outputs** (lamps) + **Inputs in menu order** → full LID/routine↔name map.
BCU/ACE/gearbox/airbag: same submenu structure (faults/settings/inputs/outputs/utility).
