"""ACE (Lucas) reference tool menu + our coverage — drives the Map tab.

status: "ok" (confirmed in our code/decoding), "maybe" (reference/text known but raw not
captured by us), "todo" (not mapped yet). `ref` = LID/routine/command or next step.
Menu order preserved exactly from the reference tool (see `references/reference_tool_master_menu.md`,
ACE section). Nothing is "ok" yet — ACE has not been sniffed yet.

⚠️ ACE caveat: the reference tool's valve codes are unreliable (pressure sensor faults show up as
"control valve" faults). Outputs activate real valves/warning lamp and Utility
calibrates/bleeds oil — only run stationary and read live first.
"""

ACE_MENU = [
    {"cat": "Fault codes", "items": [
        {"name": "Read faults (Faults - Read)", "status": "maybe",
         "ref": "dictionary 0001–0048; 04-02/04/05 + 06-01 seen RDL 016 via reference tool; raw not sniffed"},
        {"name": "Clear faults (Faults - Clear)", "status": "todo", "ref": "sniff separately from Read"},
    ]},
    {"cat": "Inputs — live", "items": [
        {"name": "1. Engine Speed (rpm)", "status": "todo", "ref": ""},
        {"name": "2. Road Speed (km/h)", "status": "todo", "ref": ""},
        {"name": "3. Battery Voltage (V)", "status": "todo", "ref": ""},
        {"name": "4. DCV1 Current (A)", "status": "todo", "ref": "direction valve 1"},
        {"name": "5. DCV2 Current (A)", "status": "todo", "ref": "direction valve 2"},
        {"name": "6. PCV Current (A)", "status": "todo", "ref": "pressure control valve"},
        {"name": "7. Pressure Sensor (bar)", "status": "todo", "ref": "key to the valve caveat"},
        {"name": "8. Residual Pressure (bar)", "status": "todo", "ref": ""},
        {"name": "9. System Pressure (bar)", "status": "todo", "ref": ""},
        {"name": "10. Upper Lateral Accelerometer", "status": "todo", "ref": ""},
        {"name": "11. Lower Lateral Accelerometer", "status": "todo", "ref": ""},
        {"name": "12. Ignition Switch", "status": "todo", "ref": ""},
        {"name": "13. Reverse Switch", "status": "todo", "ref": ""},
        {"name": "14. Main Relay", "status": "todo", "ref": ""},
        {"name": "15. Warning Lamp", "status": "todo", "ref": ""},
    ]},
    {"cat": "Outputs — tester ⚠️", "items": [
        {"name": "1. Main relay (Force ON)", "status": "todo", "ref": ""},
        {"name": "2. Main relay (Force OFF)", "status": "todo", "ref": ""},
        {"name": "3. Warning Lamp (ON/OFF)", "status": "todo", "ref": ""},
        {"name": "4. Dir. Control Valve 1 (ON/OFF)", "status": "todo", "ref": "⚠️ activates valve"},
        {"name": "5. Dir. Control Valve 2 (ON/OFF)", "status": "todo", "ref": "⚠️ activates valve"},
    ]},
    {"cat": "Utility ⚠️", "items": [
        {"name": "1. Calib. Accelerometer 1", "status": "todo", "ref": "⚠️ writes calibration"},
        {"name": "2. Calib. Accelerometer 2", "status": "todo", "ref": "⚠️ writes calibration"},
        {"name": "3. Set Calibrated", "status": "todo", "ref": "⚠️ writes"},
        {"name": "4. Oil Bleeding Step 1", "status": "todo", "ref": "⚠️ active procedure"},
        {"name": "5. Oil Bleeding Step 2", "status": "todo", "ref": "⚠️ active procedure"},
        {"name": "6. Oil Bleeding Step 3", "status": "todo", "ref": "⚠️ active procedure"},
    ]},
]
