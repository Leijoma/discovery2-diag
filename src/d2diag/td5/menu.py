"""TD5 (Lucas engine ECU) reference tool menu + our coverage — drives the Map tab.

status: "ok" (confirmed in our code/decoding), "maybe" (decoded but value/scale/
mapping uncertain), "todo" (not mapped/implemented). `ref` = LID/routine/command.

The menu is now **complete** from the reference tool transcription (registry repo:
`reference tool_protocol_Discovery2_Master_TD5_Complete.docx`, 2026-08-08 — Settings,
Inputs, Outputs, Utilities in exact reference tool order). Our code (`td5/`) is mapped against
it: session+unlock and 210 raw-mapped fault bits (`21 3B`) plus the fuelling signals
we decode = ok; switches, settings, outputs and security utilities = todo.

⚠️ Display values in the .docx (ABNFE, svtnp006, ENABLED/DISABLED, ROBUST …) are
the transcription's **screenshot baseline — NOT read off RDL 016**.
"""

TD5_MENU = [
    {"cat": "Connection (requires unlock)", "items": [
        {"name": "Fast init (StartCommunication)", "status": "ok", "ref": "tolerant, searches for C1"},
        {"name": "StartDiagnosticSession", "status": "ok", "ref": "0xA0"},
        {"name": "SecurityAccess (seed→key)", "status": "ok", "ref": "keygen; Ekaitza-confirmed"},
    ]},
    {"cat": "Fault codes", "items": [
        {"name": "Read faults (210 bits raw-mapped)", "status": "ok",
         "ref": "21 3B, byte*8+bit; PROVEN Ekaitza + reference tool v1.12"},
        {"name": "Clear faults", "status": "ok", "ref": "StartRoutine 0xDD + 18×00"},
        {"name": "Reference (display codes + causes)", "status": "ok", "ref": "the dictionary TD5 + Kelvin list"},
    ]},
    {"cat": "Inputs — Fuelling / live (22)", "items": [
        {"name": "1. Engine Speed (rpm)", "status": "ok", "ref": "21 09", "lid": "09", "sig": "rpm"},
        {"name": "2. Idle Speed Error (rpm)", "status": "ok", "ref": "21 21 (s16)", "lid": "21", "sig": "rpm_error"},
        {"name": "3. Road Speed (km/h)", "status": "ok", "ref": "21 0D", "lid": "0d", "sig": "speed"},
        {"name": "4. Battery (V)", "status": "ok", "ref": "21 10 (u16/1000)", "lid": "10", "sig": "battery"},
        {"name": "5. Accel. Way 1 (V)", "status": "ok", "ref": "21 1B@0", "lid": "1b", "sig": "accel_way1"},
        {"name": "6. Accel. Way 2 (V)", "status": "ok", "ref": "21 1B@2", "lid": "1b", "sig": "accel_way2"},
        {"name": "7. Accel. Way 3 (V)", "status": "maybe", "ref": "21 1B@4 — voltage trace (way3 scale requires pedal sweep)", "lid": "1b", "sig": "accel_way3"},
        {"name": "8. Accel. Supply (V)", "status": "ok", "ref": "21 1B@6", "lid": "1b", "sig": "accel_supply"},
        {"name": "9. Coolant Temp (°C)", "status": "ok", "ref": "21 1A@0", "lid": "1a", "sig": "coolant_temp"},
        {"name": "10. Fuel Temp (°C)", "status": "ok", "ref": "21 1A@12", "lid": "1a", "sig": "fuel_temp"},
        {"name": "11. Air Inlet Temp (°C)", "status": "ok", "ref": "21 1A@4 (scale not car-confirmed)", "lid": "1a", "sig": "air_temp"},
        {"name": "12. Air Flow (kg/hr)", "status": "maybe", "ref": "21 1D u16@4 — MAF, field proven (r=0.95 vs rpm×MAP); scale candidate", "lid": "1d", "sig": "maf"},
        {"name": "13. Ambient Pressure (kPa)", "status": "ok", "ref": "21 23", "lid": "23", "sig": "ambient_press_1"},
        {"name": "14. Manifold Turbo Pressure (kPa)", "status": "ok", "ref": "21 1C@0 — CONFIRMED 2026-08-03", "lid": "1c", "sig": "manifold_press"},
        {"name": "15. EGR Modulator (%)", "status": "maybe", "ref": "21 1D@15 u8 (candidate)", "lid": "1d", "sig": "egr_modulator"},
        {"name": "16. EGR Inlet (%)", "status": "todo", "ref": "21 1D@16 — constant 0 (dead/reserved byte)", "lid": "1d"},
        {"name": "17. Wastegate Modulator (%)", "status": "maybe", "ref": "21 1D@17 u8 (candidate)", "lid": "1d", "sig": "wastegate_modulator"},
        {"name": "18. Cylinder 1 (balance)", "status": "ok", "ref": "21 40@0 (s16)", "lid": "40", "sig": "balance_1"},
        {"name": "19. Cylinder 2 (balance)", "status": "ok", "ref": "21 40@2", "lid": "40", "sig": "balance_2"},
        {"name": "20. Cylinder 3 (balance)", "status": "ok", "ref": "21 40@4", "lid": "40", "sig": "balance_3"},
        {"name": "21. Cylinder 4 (balance)", "status": "ok", "ref": "21 40@6", "lid": "40", "sig": "balance_4"},
        {"name": "22. Cylinder 5 (balance)", "status": "ok", "ref": "21 40@8", "lid": "40", "sig": "balance_5"},
    ]},
    {"cat": "Inputs — switches (12)", "items": [
        {"name": "1. Brake Switch 1", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "2. Brake Switch 2", "status": "todo", "ref": "cf. pair with Brake 1 (complementary)", "lid": "1e 36"},
        {"name": "3. Clutch Switch", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "4. Transfer Ratio (HIGH/LOW)", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "5. Gear Box (P/N…)", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "6. Cruise Control", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "7. Cruise Resume", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "8. Set Accelerate", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "9. AC Clutch Request", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "10. AC Clutch Drive", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "11. AC Fan Request", "status": "todo", "ref": "", "lid": "1e 36"},
        {"name": "12. AC Fan Drive", "status": "todo", "ref": "", "lid": "1e 36"},
    ]},
    {"cat": "Settings — injector codes (6)", "items": [
        {"name": "Injector 1–5 (5-character code)", "status": "todo", "ref": "docx baseline 'ABNFE' (not RDL 016)"},
        {"name": "INJ. TYPE (read/identify)", "status": "todo", "ref": "UI action, separate from the code fields"},
    ]},
    {"cat": "Settings — read-only ID (5)", "items": [
        {"name": "Config Tune ID", "status": "todo", "ref": "docx: 'svtnp006' (not RDL 016)"},
        {"name": "Fuel Tune ID", "status": "todo", "ref": "docx: 'svdhg003'"},
        {"name": "ECU Part Number", "status": "todo", "ref": "docx: 'NNN000120'"},
        {"name": "Homologation", "status": "todo", "ref": "docx: '4213'"},
        {"name": "GET VIN", "status": "todo", "ref": "own service; read separately"},
    ]},
    {"cat": "Settings — feature/config (21)", "items": [
        {"name": "21 feature flags (packed block?)", "status": "todo",
         "ref": "Temperature Gauge…Wastegate Modulator + ECU Status(enum); toggle one at a time during capture"},
    ]},
    {"cat": "Outputs — tests ⚠️ (14)", "items": [
        {"name": "1. A/C Clutch (pulse)", "status": "ok", "ref": "30 A3 FF (sniffed 08-08)"},
        {"name": "2. A/C Fan (pulse)", "status": "ok", "ref": "30 A4 FF"},
        {"name": "3. MIL Lamp (pulse)", "status": "ok", "ref": "30 A2 FF"},
        {"name": "4. Fuel Pump (pulse)", "status": "ok", "ref": "30 A1 FF"},
        {"name": "5. Glow Plugs (pulse)", "status": "ok", "ref": "30 B3 FF"},
        {"name": "6. Pulse Rev Counter", "status": "ok", "ref": "30 B7 FF (tacho needle)"},
        {"name": "7. Wastegate Modul. (pulse)", "status": "ok", "ref": "30 BE FF 00 0A 13 88 (PWM)"},
        {"name": "8. Temp Gauge (pulse)", "status": "ok", "ref": "30 BA FF"},
        {"name": "9. EGR Throttle (pulse)", "status": "ok", "ref": "30 BD FF 00 FA 13 88 (PWM)"},
        {"name": "10–14. Injector 1–5 (single pulse)", "status": "ok", "ref": "31 C2 0<n> (sniffed)"},
    ]},
    {"cat": "Utilities ⚠️ (2)", "items": [
        {"name": "GET SECURITY STATUS", "status": "ok",
         "ref": "31 C0 + 33 C0 → 03 = not immobilised (sniffed/coded)"},
        {"name": "LEARN SECURITY CODE", "status": "todo",
         "ref": "🔴 can change immobiliser state — not implemented, NEVER run during testing"},
    ]},
]
