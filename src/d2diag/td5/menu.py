"""TD5 (Lucas motor-ECU) reference tool-meny + vår täckning — driver Karta-fliken.

status: "ok" (bekräftat i vår kod/avkodning), "maybe" (avkodat men värde/skala
osäker), "todo" (ej mappat/implementerat). `ref` = LID/rutin/kommando.

TD5 är vår mest utvecklade modul: full session+unlock, 210 rå-mappade felbitar
(`21 3B`) och live-signaler ur `td5/identifiers.py`. Outputs/Service är ännu ej
implementerade (och reference tools fulla input-/output-lista är inte transkriberad).
Källor: vår kod (`td5/`), `references/td5_fault_codes.md`, dicten (TD5-sektionen).
"""

TD5_MENU = [
    {"cat": "Uppkoppling (kräver unlock)", "items": [
        {"name": "Fast init (StartCommunication)", "status": "ok", "ref": "tolerant, söker C1"},
        {"name": "StartDiagnosticSession", "status": "ok", "ref": "0xA0"},
        {"name": "SecurityAccess (seed→key)", "status": "ok", "ref": "keygen; Ekaitza-bekräftad"},
    ]},
    {"cat": "Felkoder", "items": [
        {"name": "Läs fel (210 bitar rå-mappade)", "status": "ok",
         "ref": "21 3B, byte*8+bit; BELAGT Ekaitza + reference tool v1.12"},
        {"name": "Radera fel", "status": "ok", "ref": "StartRoutine 0xDD + 18×00"},
        {"name": "Facit (display-koder + orsaker)", "status": "ok", "ref": "dicten TD5 + Kelvin-lista"},
    ]},
    {"cat": "Inputs — live (avkodade)", "items": [
        {"name": "Engine speed (rpm)", "status": "ok", "ref": "21 09"},
        {"name": "Road speed (km/h)", "status": "ok", "ref": "21 0D"},
        {"name": "Battery (V)", "status": "ok", "ref": "21 10 (u16/1000)"},
        {"name": "Coolant temp (°C)", "status": "ok", "ref": "21 1A@0"},
        {"name": "Inlet air temp (°C)", "status": "ok", "ref": "21 1A@4 (skala ej bilbekräftad)"},
        {"name": "Fuel temp (°C)", "status": "ok", "ref": "21 1A@12"},
        {"name": "Ambient/ext temp (°C)", "status": "maybe", "ref": "21 1A@8 — givare ej monterad (150°C default)"},
        {"name": "Gaspedal: 2 spår + demand% + 5V-ref", "status": "ok", "ref": "21 1B"},
        {"name": "Manifold pressure / MAP (bar)", "status": "ok", "ref": "21 1C@0 — BEKRÄFTAT mot bil 2026-08-03"},
        {"name": "MAF (rå)", "status": "maybe", "ref": "21 1C@4 — ingen MAF-givare på denna ROM"},
        {"name": "RPM error", "status": "ok", "ref": "21 21 (s16)"},
        {"name": "Ambient pressure 1/2 (bar)", "status": "ok", "ref": "21 23"},
        {"name": "Injektorbalans 1–5", "status": "ok", "ref": "21 40 (s16 ×5)"},
    ]},
    {"cat": "Inputs — reference tool (ej avkodade)", "items": [
        {"name": "Övriga live-inputs (glödstift, EGR-läge, wastegate-duty, boost-mål …)",
         "status": "todo", "ref": "reference tools fulla input-lista ej transkriberad/sniffad"},
    ]},
    {"cat": "Settings / ID", "items": [
        {"name": "Läs ECU-ID / mjukvara / VIN", "status": "todo", "ref": "ej implementerat för TD5"},
        {"name": "Skriv settings", "status": "todo", "ref": "⚠️ ej implementerat"},
    ]},
    {"cat": "Outputs — tester ⚠️", "items": [
        {"name": "Drivsteg (glödstiftsrelä, kylfläkt, AC, MIL, tacho …)", "status": "todo",
         "ref": "⚠️ ej implementerat; reference tools output-lista ej transkriberad"},
    ]},
    {"cat": "Utility / Service ⚠️", "items": [
        {"name": "Injektorkodning (CR-trim)", "status": "todo", "ref": "⚠️ känsligt — skriver"},
        {"name": "Reset adaptions", "status": "todo", "ref": "⚠️ skriver"},
        {"name": "Immobiliser / synk", "status": "todo", "ref": "⚠️ skriver"},
    ]},
]
