"""SLABS reference tool-meny + vår täckning — enda källan för referens-/täckningssidan.

Under sniffning: kör → analysera → **uppdatera status/ref här** → repeat. Dashboardens
"Karta"-flik renderar detta. status: "ok" (bekräftat i kod/avkodning), "maybe"
(troligt, ej verifierat), "todo" (ej mappat än). `ref` = LID/rutin/kommando.
Källa till menyn: ägarens `Discovery 2/reference tool.txt`. Se `references/reference tool_menu_map.md`.

Uppdatering 2026-08-08: full per-input-svep sniffad (session.log). **Alla input-
LID:er identifierade** — SLS analog `21 53/54/55`, ABS analog `21 43/44/49/50/57`,
switchar `21 42/48/56/58`. Därför `todo`→`maybe` för dessa (rått fångat, offset/
skala ej isolerad än). `any-door` avkodad (`21 56` byte0) via differential → `ok`.
"""

SLABS_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Loggade fel", "status": "ok", "ref": "21 11 (bit-per-fel)"},
        {"name": "Aktuella fel", "status": "ok", "ref": "21 47"},
        {"name": "Radera fel", "status": "ok", "ref": "14 FF FF → 54"},
    ]},
    {"cat": "Settings", "items": [
        {"name": "Test status (en/dis)", "status": "maybe", "ref": "21 45/46/49/59 (sniffat 08-08; bytes ej isolerade)"},
        {"name": "ECU calibrated (yes/no)", "status": "maybe", "ref": "settings-block sniffat"},
        {"name": "Transport mode (en/dis)", "status": "maybe", "ref": "settings-block sniffat"},
        {"name": "Suspension type (AIR/springs)", "status": "maybe", "ref": "settings-block sniffat"},
    ]},
    {"cat": "Inputs — ABS", "items": [
        {"name": "ABS-sensor FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 50 (4 byte ~×0,02 V)"},
        {"name": "Hjulhastighet FR/FL/RR/RL", "status": "maybe", "ref": "21 43"},
        {"name": "Inlet valve FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 44/49/57 (sniffat 08-08; offset ej isolerat)"},
        {"name": "Outlet valve FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Pump monitor (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Pump relay (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Battery (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "ECU internal supply (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Ground Reference (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Engine speed (rpm)", "status": "maybe", "ref": "21 44/49/57 (via CAN)"},
        {"name": "Engine Torque (Nm)", "status": "maybe", "ref": "21 44/49/57 (via CAN)"},
        {"name": "Throttle Position (%)", "status": "maybe", "ref": "21 44/49/57 (via CAN)"},
        {"name": "HDC Brake (V)", "status": "maybe", "ref": "21 44/49/57"},
        {"name": "Shuttle Switch", "status": "maybe", "ref": "21 42/48/56/58 (switch-block)"},
    ]},
    {"cat": "Inputs — SLS", "items": [
        {"name": "Left/Right Sensor Value (höjd)", "status": "ok", "ref": "21 54 b0/b1"},
        {"name": "Left/Right Sensor Supply (V)", "status": "maybe", "ref": "21 53/55 (sniffat 08-08)"},
        {"name": "Left/Right Value (V)", "status": "maybe", "ref": "21 53/55"},
        {"name": "Exhaust Valve (V)", "status": "maybe", "ref": "21 53/55"},
        {"name": "Compressor Relay (V)", "status": "maybe", "ref": "21 53/55"},
    ]},
    {"cat": "Inputs — Switchar", "items": [
        {"name": "Any Door (öppen/stängd)", "status": "ok", "ref": "21 56 byte0 bit0 — BELAGT diff 08-08 (00 stängd/01 öppen)"},
        {"name": "Neutral/LowRange/DiffLock/Reverse/HDC/Shuttle", "status": "maybe", "ref": "21 42/48/56/58 (stod i default → bit ej isolerad)"},
        {"name": "Plip signal", "status": "maybe", "ref": "21 42/48/56/58"},
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
