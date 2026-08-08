"""Auto Gearbox GS8.87.0 (Bosch, ZF4HP22-24) reference tool-meny + vår täckning.

status: "ok" (bekräftat i vår kod), "maybe" (facit känd men rå ej fångad), "todo".
Menyordning bevarad exakt från reference tool (se `references/reference tool_master_menu.md`,
avsnitt Auto Gearbox). Inget "ok" än — EAT gick **inte** att läsa med lånade
reference tool 1 (2026-08-07), så rå-frames saknas helt. Felkodslistan i dicten (39 RAVE
P-koder) är official + forumbekräftad, men inte on-wire-verifierad av oss.
"""

AUTOBOX_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (Faults - Read)", "status": "maybe",
         "ref": "dicten 39 P-koder (RAVE, official) + forumbekräftad the factory tool 1–39; EJ läsbar m. reference tool 1; rå ej sniffad"},
        {"name": "Radera fel (Faults - Clear)", "status": "todo", "ref": "sniffa separat från Read"},
    ]},
    {"cat": "Inputs — general (26)", "items": [
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
