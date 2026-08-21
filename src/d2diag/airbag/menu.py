"""Airbag (TRW SPS Type 2A) reference tool menu + our coverage — drives the Map tab.

status: "ok" (confirmed in our code), "maybe" (reference known but raw not captured), "todo".
Menu order preserved exactly from the reference tool (see `references/reference_tool_master_menu.md`,
Airbag section). The ECU is limited: Read/Clear Faults + Settings (ID/config) —
**no** live Inputs or Outputs page is assumed.

🔴 SAFETY: SRS is pyrotechnics. **Read only** — NEVER activate any output/
firing circuit. Our sniffer is RX-only. Only clear faults once the fault is fixed.
"""

AIRBAG_MENU = [
    {"cat": "Fault codes", "items": [
        {"name": "Read faults (Faults - Read)", "status": "maybe",
         "ref": "dictionary: position=display code solved (1–65); 004 + 022 seen RDL 016 via reference tool; raw not sniffed"},
        {"name": "Clear faults (Faults - Clear)", "status": "todo",
         "ref": "⚠️ only after repair; sniff separately from Read"},
    ]},
    {"cat": "Settings — ID/config (read)", "items": [
        {"name": "1. Manufacturer", "status": "todo", "ref": ""},
        {"name": "2. Model", "status": "todo", "ref": ""},
        {"name": "3. Software version", "status": "todo", "ref": ""},
        {"name": "4. Hardware version", "status": "todo", "ref": ""},
        {"name": "5. Serial number", "status": "todo", "ref": ""},
        {"name": "6. Date of build", "status": "todo", "ref": ""},
        {"name": "7. Part reference", "status": "todo", "ref": ""},
        {"name": "8. Part number", "status": "todo", "ref": ""},
        {"name": "9. VIN", "status": "todo", "ref": "the only documented writable one — read only"},
        {"name": "10. Driver's airbag (present)", "status": "todo", "ref": ""},
        {"name": "11. Passenger's airbag (present)", "status": "todo", "ref": ""},
        {"name": "12. Right hand Pretensioner", "status": "todo", "ref": ""},
        {"name": "13. Left hand Pretensioner", "status": "todo", "ref": ""},
        {"name": "14. Driver's side airbag", "status": "todo", "ref": ""},
        {"name": "15. Passenger's side airbag", "status": "todo", "ref": ""},
        {"name": "16. Rolamites", "status": "todo", "ref": "crash sensors"},
    ]},
    {"cat": "Outputs / Utility", "items": [
        {"name": "No output/utility page 🔴", "status": "ok",
         "ref": "proven: TRW SPS 2A has no output tests — never activate a firing circuit"},
    ]},
]
