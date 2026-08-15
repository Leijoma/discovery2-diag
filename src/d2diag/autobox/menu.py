"""Auto Gearbox GS8.87.0 (Bosch, ZF4HP22-24) reference tool-meny + vår täckning.

status: "ok" (bekräftat i vår kod), "maybe" (facit känd men rå ej fångad), "todo".
Menyordning bevarad exakt från reference tool (se `references/reference_tool_master_menu.md`,
avsnitt Auto Gearbox). **Eget protokoll (`72`-ramat)** — sniffat 2026-08-10:
reference tool sa "unable to perform the function" MEN ECU:n SVARAR med datablock.
Funktions-ID:n belagda (nedan); innehållstolkning väntar på lyckad session.
Felkodslistan i dicten (39 RAVE P-koder) är official + forumbekräftad.
"""

AUTOBOX_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (Faults - Read)", "status": "maybe",
         "ref": "cmd 72 05 04 00 73 belagt (ECU svarar 72 09 60 …); dicten 39 P-koder; innehåll TBD"},
        {"name": "Radera fel (Faults - Clear)", "status": "maybe", "ref": "cmd 72 04 05 73 belagt"},
    ]},
    {"cat": "Inputs — general (26)", "items": [
        # inputs läses via 72 05 0B 00 (pressure) / 72 05 0B 03 (general); svar 72 16 60 … (bulk)

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
    {"cat": "Outputs — tester ⚠️", "items": [
        {"name": "Outputs (ej dokumenterade)", "status": "todo",
         "ref": "meny ej transkriberad — screenshota/sniffa; ⚠️ solenoider"},
    ]},
    {"cat": "Utility", "items": [
        {"name": "Utility (ej dokumenterade)", "status": "todo",
         "ref": "adaptioner/reset — meny ej transkriberad; ⚠️ skriver"},
    ]},
]
