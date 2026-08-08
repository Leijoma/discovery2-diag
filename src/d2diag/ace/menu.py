"""ACE (Lucas) reference tool-meny + vår täckning — driver Karta-fliken.

status: "ok" (bekräftat i vår kod/avkodning), "maybe" (facit/text känd men rå ej
fångad av oss), "todo" (ej mappat än). `ref` = LID/rutin/kommando eller nästa steg.
Menyordning bevarad exakt från reference tool (se `references/reference tool_master_menu.md`,
avsnitt ACE). Inget är "ok" än — ACE är ännu inte sniffad.

⚠️ ACE-caveat: reference tools ventilkoder är opålitliga (tryckgivarfel visas som
"control valve"-fel). Outputs aktiverar riktiga ventiler/varningslampa och Utility
kalibrerar/oljeluftar — kör bara stillastående och läs live först.
"""

ACE_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (Faults - Read)", "status": "maybe",
         "ref": "dicten 0001–0048; 04-02/04/05 + 06-01 sett RDL 016 via reference tool; rå ej sniffad"},
        {"name": "Radera fel (Faults - Clear)", "status": "todo", "ref": "sniffa separat från Read"},
    ]},
    {"cat": "Inputs — live", "items": [
        {"name": "1. Engine Speed (rpm)", "status": "todo", "ref": ""},
        {"name": "2. Road Speed (km/h)", "status": "todo", "ref": ""},
        {"name": "3. Battery Voltage (V)", "status": "todo", "ref": ""},
        {"name": "4. DCV1 Current (A)", "status": "todo", "ref": "riktningsventil 1"},
        {"name": "5. DCV2 Current (A)", "status": "todo", "ref": "riktningsventil 2"},
        {"name": "6. PCV Current (A)", "status": "todo", "ref": "tryckreglerventil"},
        {"name": "7. Pressure Sensor (bar)", "status": "todo", "ref": "nyckel för ventil-caveat"},
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
        {"name": "4. Dir. Control Valve 1 (ON/OFF)", "status": "todo", "ref": "⚠️ aktiverar ventil"},
        {"name": "5. Dir. Control Valve 2 (ON/OFF)", "status": "todo", "ref": "⚠️ aktiverar ventil"},
    ]},
    {"cat": "Utility ⚠️", "items": [
        {"name": "1. Calib. Accelerometer 1", "status": "todo", "ref": "⚠️ skriver kalibrering"},
        {"name": "2. Calib. Accelerometer 2", "status": "todo", "ref": "⚠️ skriver kalibrering"},
        {"name": "3. Set Calibrated", "status": "todo", "ref": "⚠️ skriver"},
        {"name": "4. Oil Bleeding Step 1", "status": "todo", "ref": "⚠️ aktiv procedur"},
        {"name": "5. Oil Bleeding Step 2", "status": "todo", "ref": "⚠️ aktiv procedur"},
        {"name": "6. Oil Bleeding Step 3", "status": "todo", "ref": "⚠️ aktiv procedur"},
    ]},
]
