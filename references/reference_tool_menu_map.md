# reference tool-menykarta (RDL 016) + korsning mot sniffat protokoll

Källa: ägarens `Discovery 2/reference tool.txt` — menyerna i den lånade reference toolen (reference tool 1).
Detta är **indexet** för att avkoda vilka `21 xx`-LID:ar / `31 xx`-rutiner som är vad.

## Moduler (denna bils reference tool)
TD5 · Motronic (*V8, kräver unlock — ej denna bil*) · **SLABS** · **VALEO BCU** ·
**ACE** · **D2 AUTOGEARBOX** · **Airbag**

**Gemensam submeny per modul:** Faults (read/clear) · Settings (read/write) ·
Inputs · Outputs (ventiler/lampor on/off) · Utility (modulspecifikt).
⇒ Samma struktur att sniffa för BCU/ACE/gearbox/airbag.

## SLABS — inputs (reference tool-ordning) ↔ våra LID:ar
Settings (bekräftat sniffat): test status en/dis · ecu calibrated · transport mode ·
suspension type AIR/springs.

**Inputs-listan** (reference tool): ABS-sensor FR/FL/RR/RL · hjulhastighet FR/FL/RR/RL ·
inlet valve ×4 · outlet valve ×4 · pump monitor (V) · pump relay (V) · Battery (V) ·
ECU internal supply (V) · Ground Reference (V) · Engine speed (rpm) · Engine Torque ·
Throttle % · HDC Brake (V) · Shuttle Switch · Left/Right Sensor Value · Left/Right
Sensor Supply (V) · Left/Right Value (V) · Exhaust Valve (V) · Compressor Relay (V) ·
Neutral/Low Range/Diff Lock/Reverse/HDC/Any Door Switch · Plip signal.

**Korsning mot fångade `21 xx`** (belagt / troligt / att bekräfta):
| LID | Fångade bytes | Trolig tolkning |
|---|---|---|
| `21 54` | `91 9c 0f 0f` | ✅ **Left/Right Sensor Value** (höjder): b0=145≈vä, b1=156≈hö (matchar baslinjen L143/R157) |
| `21 50` | `72 73 73 72` | ✅ **ABS-sensor FR/FL/RR/RL** (V): 0x72≈114 → ~2,28 V (spec 2,0–2,4 V) |
| `21 43` | `7c 00 7c 00 7c 00 7c 00` | **hjulhastighet FR/FL/RR/RL** (0 stillastående) |
| `21 44` | `00 80 01 02 01 01 02 01 02 02 03 04 …` | inlet/outlet-ventil-spänningar (8 st)? att bekräfta |
| `21 53` | `d2 d2 0f 0f` | Left/Right Sensor Supply el. Value (V)? att bekräfta |
| `21 42/48/56/58` | `82` / `94 61` / … | switch-block (Neutral/Diff/HDC/Shuttle…)? att bekräfta |
| `21 11` | 16-byte bitfält | ✅ **loggade fel** · `21 47` = aktuella |
Övriga (`21 45/46/49/55/57/59`) = fler input-fält — mappas när vi läser i menyordning.

## SLABS — Outputs (on/off) — reference tool-ordning
FR/FL/RR/RL **Inlet/Outlet Valve** (8) · SLS **Left/Right/Exhaust valve** · **ABS Pump
relay** · **Speedometer** · **SLS Compressor** · **SLS Buzzer** · **T.C. Lamp** · **ABS
Warning Light** · **HDC Warning Light** · **Brake Warning Light** · **SLS lamps** ·
**Offroad Lamp** · **HDC Fault lamps** · **HDC Brake lamps**.

**Belagt (sniffat) `31 xx`-rutiner:** exhaust=`2F` · compressor=`30` · buzzer=`31` ·
pump relay=`25` · hjul-ventiltest=`22 <sub>`. **Lamporna (T.C./ABS/HDC/Brake/SLS/
Offroad) = fångades EJ rent** (första loggen skräp) → **re-logga Outputs i listordning
ovan** så mappas varje lampa → `31 xx`.

## SLABS — Utility
ABS Bleeding-tester · **Power Bleed** (`31 22 04 …`) · **Modulator Bleed**
(`31 22 11/12/13/14 …`) · **FR/FL/RR/RL Test** (`31 22 <sub> <mask> c1 f4`, mask =
hjul-bitmask) · **SLS height calibration** · **Raise/Lower Left/Right** (`31 33-36`) ·
**Store heights** (⚠️ skriver kalibrering — rör ej).

## Nästa
Re-logga **Outputs** (lampor) + **Inputs i menyordning** → full LID/rutin↔namn-karta.
BCU/ACE/gearbox/airbag: samma submenystruktur (faults/settings/inputs/outputs/utility).
