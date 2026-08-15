"""Airbag (TRW SPS Type 2A) reference tool-meny + vår täckning — driver Karta-fliken.

status: "ok" (bekräftat i vår kod), "maybe" (facit känd men rå ej fångad), "todo".
Menyordning bevarad exakt från reference tool (se `references/reference_tool_master_menu.md`,
avsnitt Airbag). ECU:n är begränsad: Read/Clear Faults + Settings (ID/config) —
**ingen** live Inputs- eller Outputs-sida antas.

🔴 SÄKERHET: SRS är pyroteknik. **Läs endast** — aktivera ALDRIG någon output/
tändkrets. Vår sniffer är RX-only. Radera fel först när felet är åtgärdat.
"""

AIRBAG_MENU = [
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (Faults - Read)", "status": "maybe",
         "ref": "dicten: position=display-kod löst (1–65); 004 + 022 sett RDL 016 via reference tool; rå ej sniffad"},
        {"name": "Radera fel (Faults - Clear)", "status": "todo",
         "ref": "⚠️ endast efter åtgärd; sniffa separat från Read"},
    ]},
    {"cat": "Settings — ID/konfig (läs)", "items": [
        {"name": "1. Manufacturer", "status": "todo", "ref": ""},
        {"name": "2. Model", "status": "todo", "ref": ""},
        {"name": "3. Software version", "status": "todo", "ref": ""},
        {"name": "4. Hardware version", "status": "todo", "ref": ""},
        {"name": "5. Serial number", "status": "todo", "ref": ""},
        {"name": "6. Date of build", "status": "todo", "ref": ""},
        {"name": "7. Part reference", "status": "todo", "ref": ""},
        {"name": "8. Part number", "status": "todo", "ref": ""},
        {"name": "9. VIN", "status": "todo", "ref": "enda dokumenterat skrivbara — läs bara"},
        {"name": "10. Driver's airbag (present)", "status": "todo", "ref": ""},
        {"name": "11. Passenger's airbag (present)", "status": "todo", "ref": ""},
        {"name": "12. Right hand Pretensioner", "status": "todo", "ref": ""},
        {"name": "13. Left hand Pretensioner", "status": "todo", "ref": ""},
        {"name": "14. Driver's side airbag", "status": "todo", "ref": ""},
        {"name": "15. Passenger's side airbag", "status": "todo", "ref": ""},
        {"name": "16. Rolamites", "status": "todo", "ref": "krocksensorer"},
    ]},
    {"cat": "Outputs / Utility", "items": [
        {"name": "Ingen output/utility-sida 🔴", "status": "ok",
         "ref": "belagt: TRW SPS 2A saknar output-tester — aktivera aldrig tändkrets"},
    ]},
]
