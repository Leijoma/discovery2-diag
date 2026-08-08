"""SLABS reference tool-meny + vår täckning — enda källan för referens-/täckningssidan.

Under sniffning: kör → analysera → **uppdatera status/ref här** → repeat. Dashboardens
"Karta"-flik renderar detta. status: "ok" (bekräftat i kod/avkodning), "maybe"
(troligt, ej verifierat), "todo" (ej mappat än). `ref` = LID/rutin/kommando.
Källa till menyn: ägarens `Discovery 2/reference tool.txt`. Se `references/reference tool_menu_map.md`.
"""

SLABS_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Loggade fel", "status": "ok", "ref": "21 11 (bit-per-fel)"},
        {"name": "Aktuella fel", "status": "ok", "ref": "21 47"},
        {"name": "Radera fel", "status": "ok", "ref": "14 FF FF → 54"},
    ]},
    {"cat": "Settings", "items": [
        {"name": "Test status (en/dis)", "status": "todo", "ref": "värde känt, bytes ej mappade"},
        {"name": "ECU calibrated (yes/no)", "status": "todo", "ref": ""},
        {"name": "Transport mode (en/dis)", "status": "todo", "ref": ""},
        {"name": "Suspension type (AIR/springs)", "status": "todo", "ref": ""},
    ]},
    {"cat": "Inputs — ABS", "items": [
        {"name": "ABS-sensor FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 50 (4 byte ~×0,02 V)"},
        {"name": "Hjulhastighet FR/FL/RR/RL", "status": "maybe", "ref": "21 43"},
        {"name": "Inlet valve FR/FL/RR/RL (V)", "status": "todo", "ref": ""},
        {"name": "Outlet valve FR/FL/RR/RL (V)", "status": "todo", "ref": ""},
        {"name": "Pump monitor (V)", "status": "todo", "ref": ""},
        {"name": "Pump relay (V)", "status": "todo", "ref": ""},
        {"name": "Battery (V)", "status": "todo", "ref": ""},
        {"name": "ECU internal supply (V)", "status": "todo", "ref": ""},
        {"name": "Ground Reference (V)", "status": "todo", "ref": ""},
        {"name": "Engine speed (rpm)", "status": "todo", "ref": ""},
        {"name": "Engine Torque (Nm)", "status": "todo", "ref": ""},
        {"name": "Throttle Position (%)", "status": "todo", "ref": ""},
        {"name": "HDC Brake (V)", "status": "todo", "ref": ""},
        {"name": "Shuttle Switch", "status": "todo", "ref": ""},
    ]},
    {"cat": "Inputs — SLS", "items": [
        {"name": "Left/Right Sensor Value (höjd)", "status": "ok", "ref": "21 54 b0/b1"},
        {"name": "Left/Right Sensor Supply (V)", "status": "todo", "ref": "21 53?"},
        {"name": "Left/Right Value (V)", "status": "todo", "ref": ""},
        {"name": "Exhaust Valve (V)", "status": "todo", "ref": ""},
        {"name": "Compressor Relay (V)", "status": "todo", "ref": ""},
    ]},
    {"cat": "Inputs — Switchar", "items": [
        {"name": "Neutral/LowRange/DiffLock/Reverse/HDC/AnyDoor", "status": "todo", "ref": "21 42/48/56/58?"},
        {"name": "Plip signal", "status": "todo", "ref": ""},
    ]},
    {"cat": "Outputs — ventiler/reläer", "items": [
        {"name": "FR/FL/RR/RL Inlet+Outlet Valve (8)", "status": "todo", "ref": ""},
        {"name": "SLS Left/Right valve", "status": "todo", "ref": ""},
        {"name": "SLS Exhaust valve", "status": "ok", "ref": "31 2F"},
        {"name": "ABS Pump relay", "status": "ok", "ref": "31 25 08 fa / 02 fa"},
        {"name": "Speedometer", "status": "todo", "ref": ""},
        {"name": "SLS Compressor", "status": "ok", "ref": "31 30"},
        {"name": "SLS Buzzer", "status": "ok", "ref": "31 31"},
    ]},
    {"cat": "Outputs — lampor", "items": [
        {"name": "T.C. Lamp", "status": "todo", "ref": "re-logga Outputs i menyordning"},
        {"name": "ABS Warning Light", "status": "todo", "ref": ""},
        {"name": "HDC Warning Light", "status": "todo", "ref": ""},
        {"name": "Brake Warning Light", "status": "todo", "ref": ""},
        {"name": "SLS lamps", "status": "todo", "ref": ""},
        {"name": "Offroad Lamp", "status": "todo", "ref": ""},
        {"name": "HDC Fault lamps", "status": "todo", "ref": ""},
        {"name": "HDC Brake lamps", "status": "todo", "ref": ""},
    ]},
    {"cat": "Utility", "items": [
        {"name": "Power Bleed", "status": "ok", "ref": "31 22 04 …"},
        {"name": "Modulator Bleed", "status": "ok", "ref": "31 22 11-14 …"},
        {"name": "FR/FL/RR/RL Test", "status": "ok", "ref": "31 22 <sub> <mask> c1 f4"},
        {"name": "Raise/Lower Left/Right", "status": "ok", "ref": "31 33-36"},
        {"name": "SLS height calibration", "status": "todo", "ref": ""},
        {"name": "Store heights", "status": "todo", "ref": "⚠️ skriver kalibrering"},
    ]},
]
