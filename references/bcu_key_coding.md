# BCU — EKA-kod (läsa/sätta) + nyckelkodning (mål & research)

Valeo BCU (immobiliser/centralelektronik). Slow init, permanent matad. Ännu **ej
sniffad** — detta är målbild + plan. Två nivåer, olika risk.

## ⭐ HUVUDMÅL: läsa EKA-koden (LÅGRISK — läsoperation)
**EKA (Emergency Key Access)** = en 4-siffrig kod. Känner man den kommer man
**förbi immobilisern** via förardörrens nödöppningsprocedur (utan reference tool, om bilen
låst sig). Att **läsa** koden ur BCU:n är en ren läsning → **ofarligt**.

**reference tool-metoden (att sniffa):**
1. Koppla in, **tändning läge II**.
2. Meny → **Valeo Body Control Unit**.
3. Bläddra i sidled → **"Read-set EKA"** → ENT.
4. Bilens **4-siffriga EKA-kod visas**.
5. (Valfritt) MOD → skriv över med t.ex. `1-2-3-4` så man aldrig låser sig ute.

**Vår plan (medan reference toolen finns):**
1. Sniffa **BCU-init** (slow init-adress ~0x40 + keybytes; jfr slow-svepet).
2. Sniffa **"Read-set EKA"-läsningen** → fånga exakt request + svaret som bär de 4
   siffrorna. Ren läsning → säkert att fånga och att implementera.
3. Implementera `bcu.read_eka()` i ett `d2diag.bcu`-lager.
4. (Sekundärt) `bcu.set_eka(code)` — en definierad *write* men återställbar (byt till
   känt värde). Bakom explicit bekräftelse.

## Tändnings-egenhet (verifiera vid BCU-sniff)
Metoden ovan säger **tändning läge II** för EKA. Men BCU:n svarar generellt även med
tändning AV, och användaren minns en sekvens "**tändning av → init → tändning på**"
för någon funktion. **Fånga init:en i olika tändningslägen** vid loggning och notera
vad EKA-läsningen faktiskt kräver.

## ⚠️ SEKUNDÄRT (HÖGRISK): nyckel-/transponderprogrammering
Att programmera in en helt **ny nyckel** är den riktiga brick-zonen:
> *"A LOCKED BCU CANNOT BE UNLOCKED BY DIAGNOSTIC METHODS."*
Görs bara med **EKA känd + reservnyckel + stabil ström**, aldrig avbruten. Kräver
sniff av en riktig nyckel-session + ev. säkerhetsalgoritm (seed→key). **Först när
EKA-läsning + BCU-läsprotokollet är på plats.**

## Status
BCU ej sniffad. Känt: slow init, permanent matad, läses av denna bils reference tool 1.
**Nästa:** logga BCU med ESP32-tappen — init + **Read-set EKA** + övriga läs-funktioner.
Se [[valeo_bcu_capabilities.md]], `references/d2_diagnostic_overview.md`.
