"""SLABS reference tool menu + our coverage — the single source for the reference/coverage page.

While sniffing: run → analyse → **update status/ref here** → repeat. The dashboard's
"Map" tab renders this. status: "ok" (confirmed in code/decoding), "maybe"
(likely, not verified), "todo" (not mapped yet). `ref` = LID/routine/command.
Source of the menu: the owner's `Discovery 2/reference tool.txt`. See `references/reference_tool_menu_map.md`.

Update 2026-08-08: full per-input sweep sniffed (session.log). **All input
LIDs identified** — SLS analog `21 53/54/55`, ABS analog `21 43/44/49/50/57`,
switches `21 42/48/56/58`. Hence `todo`→`maybe` for these (captured raw, offset/
scale not isolated yet). `any-door` decoded (`21 56` byte0) via differential → `ok`.
"""

SLABS_MENU = [
    {"cat": "Fault codes", "items": [
        {"name": "Logged faults", "status": "ok", "ref": "21 11 (bit-per-fault)"},
        {"name": "Current faults", "status": "ok", "ref": "21 47"},
        {"name": "Clear faults", "status": "ok", "ref": "14 FF FF → 54"},
    ]},
    {"cat": "Settings", "items": [
        # 4 settings LIDs with STABLE raw bytes (RDL 016). ⚠️ Which LID = which
        # setting (test status / transport / ECU calibrated / suspension) is NOT solved:
        # two order-based labellings (2026-08-08 vs -09) contradict each other —
        # the card order is not stable. Solution = DIFFERENTIAL: toggle ONE setting in
        # the reference tool → see which of 45/46/49/59 has its raw byte change = that LID + the encoding.
        {"name": "Settings 21 45 (1 byte)", "status": "maybe", "ref": "raw byte 7f — one of the 4 settings (pairing unsolved)", "lid": "45"},
        {"name": "Settings 21 46 (2 byte)", "status": "maybe", "ref": "raw byte 78 76 — ditto", "lid": "46"},
        {"name": "Settings 21 49 (3 byte)", "status": "maybe", "ref": "raw byte 00 00 01 — ditto", "lid": "49"},
        {"name": "Settings 21 59 (4 byte)", "status": "maybe", "ref": "raw byte 00 0f 0f 0f — ditto", "lid": "59"},
        {"name": "Left/Right stored height", "status": "todo",
         "ref": "⚠️ 21 54 = LIVE height (149/161), NOT stored (149/149) — stored source not captured"},
    ]},
    {"cat": "Inputs — ABS", "items": [
        {"name": "ABS sensor FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 50 (4 byte ~×0.02 V)", "lid": "50"},
        {"name": "Wheel speed FR/FL/RR/RL", "status": "maybe", "ref": "21 43", "lid": "43"},
        {"name": "Inlet valve FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 44/49/57 (offset not isolated)", "lid": "44 49 57"},
        {"name": "Outlet valve FR/FL/RR/RL (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Pump monitor (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Pump relay (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Battery (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "ECU internal supply (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Ground Reference (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Engine speed (rpm)", "status": "maybe", "ref": "21 44/49/57 (via CAN)", "lid": "44 49 57"},
        {"name": "Engine Torque (Nm)", "status": "maybe", "ref": "21 44/49/57 (via CAN)", "lid": "44 49 57"},
        {"name": "Throttle Position (%)", "status": "maybe", "ref": "21 44/49/57 (via CAN)", "lid": "44 49 57"},
        {"name": "HDC Brake (V)", "status": "maybe", "ref": "21 44/49/57", "lid": "44 49 57"},
        {"name": "Shuttle Switch", "status": "maybe", "ref": "21 42/48/56/58 (switch block)", "lid": "42 48 56 58"},
    ]},
    {"cat": "Inputs — SLS", "items": [
        {"name": "Left/Right Sensor Value (height)", "status": "ok", "ref": "21 54 b0/b1", "lid": "54"},
        {"name": "Left/Right Sensor Supply (V)", "status": "maybe", "ref": "21 53/55 (sniffed 08-08)", "lid": "53 55"},
        {"name": "Left/Right Value (V)", "status": "maybe", "ref": "21 53/55", "lid": "53 55"},
        {"name": "Exhaust Valve (V)", "status": "maybe", "ref": "21 53/55", "lid": "53 55"},
        {"name": "Compressor Relay (V)", "status": "maybe", "ref": "21 53/55", "lid": "53 55"},
    ]},
    {"cat": "Inputs — Switches", "items": [
        {"name": "Any Door (open/closed)", "status": "ok", "ref": "21 56 byte0 bit0 — PROVEN (00 closed/01 open)", "lid": "56", "sig": "any_door"},
        {"name": "Neutral/LowRange/DiffLock/Reverse/HDC/Shuttle", "status": "maybe", "ref": "21 42/48/56/58 (bit not isolated)", "lid": "42 48 56 58"},
        {"name": "Plip signal", "status": "maybe", "ref": "21 42/48/56/58", "lid": "42 48 56 58"},
    ]},
    {"cat": "Outputs — valves/relays", "items": [
        {"name": "FR/FL/RR/RL Inlet+Outlet Valve (8)", "status": "todo", "ref": ""},
        {"name": "SLS Left/Right valve", "status": "todo", "ref": ""},
        {"name": "SLS Exhaust valve", "status": "ok", "ref": "31 2F"},
        {"name": "ABS Pump relay", "status": "ok", "ref": "31 25 08 fa / 02 fa"},
        {"name": "Speedometer", "status": "todo", "ref": ""},
        {"name": "SLS Compressor", "status": "ok", "ref": "31 30"},
        {"name": "SLS Buzzer", "status": "ok", "ref": "31 31"},
    ]},
    {"cat": "Outputs — lamps", "items": [
        {"name": "T.C. Lamp", "status": "todo", "ref": "re-log Outputs in menu order"},
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
        {"name": "Store heights", "status": "todo", "ref": "⚠️ writes calibration"},
    ]},
]
