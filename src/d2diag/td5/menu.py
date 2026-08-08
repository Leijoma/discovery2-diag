"""TD5 (Lucas motor-ECU) reference tool-meny + vår täckning — driver Karta-fliken.

status: "ok" (bekräftat i vår kod/avkodning), "maybe" (avkodat men värde/skala/
mappning osäker), "todo" (ej mappat/implementerat). `ref` = LID/rutin/kommando.

Menyn är nu **komplett** ur reference tool-transkriptionen (register-repot:
`reference tool_protocol_Discovery2_Master_TD5_Complete.docx`, 2026-08-08 — Settings,
Inputs, Outputs, Utilities i exakt reference tool-ordning). Vår kod (`td5/`) mappas mot
den: session+unlock och 210 rå-mappade felbitar (`21 3B`) samt de fuelling-signaler
vi avkodar = ok; switchar, settings, outputs och security-utilities = todo.

⚠️ Displayvärden i .docx (ABNFE, svtnp006, ENABLED/DISABLED, ROBUST …) är
transkriptionens **screenshot-baslinje — INTE avläst på RDL 016**.
"""

TD5_MENU = [
    {"cat": "Uppkoppling (kräver unlock)", "items": [
        {"name": "Fast init (StartCommunication)", "status": "ok", "ref": "tolerant, söker C1"},
        {"name": "StartDiagnosticSession", "status": "ok", "ref": "0xA0"},
        {"name": "SecurityAccess (seed→key)", "status": "ok", "ref": "keygen; Ekaitza-bekräftad"},
    ]},
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (210 bitar rå-mappade)", "status": "ok",
         "ref": "21 3B, byte*8+bit; BELAGT Ekaitza + reference tool v1.12"},
        {"name": "Radera fel", "status": "ok", "ref": "StartRoutine 0xDD + 18×00"},
        {"name": "Facit (display-koder + orsaker)", "status": "ok", "ref": "dicten TD5 + Kelvin-lista"},
    ]},
    {"cat": "Inputs — Fuelling / live (22)", "items": [
        {"name": "1. Engine Speed (rpm)", "status": "ok", "ref": "21 09"},
        {"name": "2. Idle Speed Error (rpm)", "status": "ok", "ref": "21 21 (s16)"},
        {"name": "3. Road Speed (km/h)", "status": "ok", "ref": "21 0D"},
        {"name": "4. Battery (V)", "status": "ok", "ref": "21 10 (u16/1000)"},
        {"name": "5. Accel. Way 1 (V)", "status": "ok", "ref": "21 1B@0 (accel_way1)"},
        {"name": "6. Accel. Way 2 (V)", "status": "ok", "ref": "21 1B@2 (accel_way2)"},
        {"name": "7. Accel. Way 3 (V)", "status": "maybe", "ref": "21 1B@4 — rättad till spänningsspår (sniff 08-08); way3-skala kräver pedalsvep"},
        {"name": "8. Accel. Supply (V)", "status": "ok", "ref": "21 1B@6 (accel_supply)"},
        {"name": "9. Coolant Temp (°C)", "status": "ok", "ref": "21 1A@0"},
        {"name": "10. Fuel Temp (°C)", "status": "ok", "ref": "21 1A@12"},
        {"name": "11. Air Inlet Temp (°C)", "status": "ok", "ref": "21 1A@4 (skala ej bilbekräftad)"},
        {"name": "12. Air Flow (gr/hr)", "status": "maybe", "ref": "21 1C@4 (maf_raw) — ingen MAF-givare/okänd skala"},
        {"name": "13. Ambient Pressure (kPa)", "status": "ok", "ref": "21 23"},
        {"name": "14. Manifold Turbo Pressure (kPa)", "status": "ok", "ref": "21 1C@0 — BEKRÄFTAT mot bil 2026-08-03"},
        {"name": "15. EGR Modulator (%)", "status": "todo", "ref": "ej avkodad"},
        {"name": "16. EGR Inlet (%)", "status": "todo", "ref": "ej avkodad"},
        {"name": "17. Wastegate Modulator (%)", "status": "todo", "ref": "ej avkodad"},
        {"name": "18. Cylinder 1 (balans)", "status": "ok", "ref": "21 40@0 (s16)"},
        {"name": "19. Cylinder 2 (balans)", "status": "ok", "ref": "21 40@2"},
        {"name": "20. Cylinder 3 (balans)", "status": "ok", "ref": "21 40@4"},
        {"name": "21. Cylinder 4 (balans)", "status": "ok", "ref": "21 40@6"},
        {"name": "22. Cylinder 5 (balans)", "status": "ok", "ref": "21 40@8"},
    ]},
    {"cat": "Inputs — switchar (12)", "items": [
        {"name": "1. Brake Switch 1", "status": "todo", "ref": ""},
        {"name": "2. Brake Switch 2", "status": "todo", "ref": "jfr par med Brake 1 (komplementära)"},
        {"name": "3. Clutch Switch", "status": "todo", "ref": ""},
        {"name": "4. Transfer Ratio (HIGH/LOW)", "status": "todo", "ref": ""},
        {"name": "5. Gear Box (P/N…)", "status": "todo", "ref": ""},
        {"name": "6. Cruise Control", "status": "todo", "ref": ""},
        {"name": "7. Cruise Resume", "status": "todo", "ref": ""},
        {"name": "8. Set Accelerate", "status": "todo", "ref": ""},
        {"name": "9. AC Clutch Request", "status": "todo", "ref": ""},
        {"name": "10. AC Clutch Drive", "status": "todo", "ref": ""},
        {"name": "11. AC Fan Request", "status": "todo", "ref": ""},
        {"name": "12. AC Fan Drive", "status": "todo", "ref": ""},
    ]},
    {"cat": "Settings — injektorkoder (6)", "items": [
        {"name": "Injektor 1–5 (5-teckens kod)", "status": "todo", "ref": "docx-baslinje 'ABNFE' (ej RDL 016)"},
        {"name": "INJ. TYPE (läs/identifiera)", "status": "todo", "ref": "UI-action, separat från kodfälten"},
    ]},
    {"cat": "Settings — read-only ID (5)", "items": [
        {"name": "Config Tune ID", "status": "todo", "ref": "docx: 'svtnp006' (ej RDL 016)"},
        {"name": "Fuel Tune ID", "status": "todo", "ref": "docx: 'svdhg003'"},
        {"name": "ECU Part Number", "status": "todo", "ref": "docx: 'NNN000120'"},
        {"name": "Homologation", "status": "todo", "ref": "docx: '4213'"},
        {"name": "GET VIN", "status": "todo", "ref": "egen tjänst; läs separat"},
    ]},
    {"cat": "Settings — feature/config (21)", "items": [
        {"name": "21 feature-flaggor (packat block?)", "status": "todo",
         "ref": "Temperature Gauge…Wastegate Modulator + ECU Status(enum); toggla en i taget vid capture"},
    ]},
    {"cat": "Outputs — tester ⚠️ (14)", "items": [
        {"name": "1. A/C Clutch (pulse)", "status": "ok", "ref": "30 A3 FF (sniffat 08-08)"},
        {"name": "2. A/C Fan (pulse)", "status": "ok", "ref": "30 A4 FF"},
        {"name": "3. MIL Lamp (pulse)", "status": "ok", "ref": "30 A2 FF"},
        {"name": "4. Fuel Pump (pulse)", "status": "ok", "ref": "30 A1 FF"},
        {"name": "5. Glow Plugs (pulse)", "status": "ok", "ref": "30 B3 FF"},
        {"name": "6. Pulse Rev Counter", "status": "ok", "ref": "30 B7 FF (tacho-nål)"},
        {"name": "7. Wastegate Modul. (pulse)", "status": "ok", "ref": "30 BE FF 00 0A 13 88 (PWM)"},
        {"name": "8. Temp Gauge (pulse)", "status": "ok", "ref": "30 BA FF"},
        {"name": "9. EGR Throttle (pulse)", "status": "ok", "ref": "30 BD FF 00 FA 13 88 (PWM)"},
        {"name": "10–14. Injector 1–5 (single pulse)", "status": "ok", "ref": "31 C2 0<n> (sniffat)"},
    ]},
    {"cat": "Utilities ⚠️ (2)", "items": [
        {"name": "GET SECURITY STATUS", "status": "ok",
         "ref": "31 C0 + 33 C0 → 03 = ej immobiliserad (sniffat/kodat)"},
        {"name": "LEARN SECURITY CODE", "status": "todo",
         "ref": "🔴 kan ändra immobiliser-state — ej implementerat, kör ALDRIG under test"},
    ]},
]
