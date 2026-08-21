"""Auto Gearbox GS8.87.0 (Bosch, ZF4HP22-24) reference tool menu + our coverage.

status: "ok" (confirmed in our code), "maybe" (reference known but raw not captured), "todo".
Menu order preserved exactly from the reference tool (see `references/reference_tool_master_menu.md`,
Auto Gearbox section). **Own protocol (`72`-framed)** — sniffed 2026-08-10:
the reference tool said "unable to perform the function" BUT the ECU RESPONDS with a data block.
Function IDs proven (below); content interpretation awaits a successful session.
The fault code list in the dictionary (39 RAVE P-codes) is official + forum-confirmed.
"""

AUTOBOX_MENU = [
    {"cat": "Fault codes", "items": [
        {"name": "Read faults (Faults - Read)", "status": "maybe",
         "ref": "cmd 72 05 04 00 73 proven (ECU responds 72 09 60 …); dictionary 39 P-codes; content TBD"},
        {"name": "Clear faults (Faults - Clear)", "status": "maybe", "ref": "cmd 72 04 05 73 proven"},
    ]},
    {"cat": "Inputs — general (26)", "items": [
        # inputs are read via 72 05 0B 00 (pressure) / 72 05 0B 03 (general); response 72 16 60 … (bulk)

        {"name": "1. Throttle position (%)", "status": "todo", "ref": ""},
        {"name": "2. Engine torque (%)", "status": "todo", "ref": ""},
        {"name": "3. Torque requested (%)", "status": "todo", "ref": ""},
        {"name": "4. Reduced torque (%)", "status": "todo", "ref": ""},
        {"name": "5. Friction torque (%)", "status": "todo", "ref": ""},
        {"name": "6. Torque reference (Nm)", "status": "todo", "ref": ""},
        {"name": "7. Gear switch W", "status": "todo", "ref": ""},
        {"name": "8. Gear switch X", "status": "todo", "ref": ""},
        {"name": "9. Gear switch Y", "status": "todo", "ref": ""},
        {"name": "10. Gear switch Z", "status": "todo", "ref": ""},
        {"name": "11. Program switch", "status": "todo", "ref": ""},
        {"name": "12. High/Low range switch", "status": "todo", "ref": ""},
        {"name": "13. Kick down", "status": "todo", "ref": ""},
        {"name": "14. Shift type", "status": "todo", "ref": ""},
        {"name": "15. Engine speed (rpm)", "status": "todo", "ref": ""},
        {"name": "16. Turbine speed (rpm)", "status": "todo", "ref": ""},
        {"name": "17. Output speed (rpm)", "status": "todo", "ref": ""},
        {"name": "18. Battery (V)", "status": "todo", "ref": ""},
        {"name": "19. Solenoid valve 1", "status": "todo", "ref": ""},
        {"name": "20. Solenoid valve 2", "status": "todo", "ref": ""},
        {"name": "21. Solenoid valve 3", "status": "todo", "ref": ""},
        {"name": "22. Modulator pressure", "status": "todo", "ref": ""},
        {"name": "23. Engine temperature (°C)", "status": "todo", "ref": ""},
        {"name": "24. Adaptive program 1", "status": "todo", "ref": ""},
        {"name": "25. Adaptive program 2", "status": "todo", "ref": ""},
        {"name": "26. Adaptive program 3", "status": "todo", "ref": ""},
    ]},
    {"cat": "Outputs — tests ⚠️", "items": [
        {"name": "Outputs (not documented)", "status": "todo",
         "ref": "menu not transcribed — screenshot/sniff; ⚠️ solenoids"},
    ]},
    {"cat": "Utility", "items": [
        {"name": "Utility (not documented)", "status": "todo",
         "ref": "adaptations/reset — menu not transcribed; ⚠️ writes"},
    ]},
]
