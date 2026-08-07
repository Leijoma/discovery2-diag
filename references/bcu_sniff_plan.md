# BCU-sniff — checklista (medan reference toolen finns)

Mål: fånga **Valeo BCU**-trafiken passivt med ESP32-tappen medan reference toolen kör.
**Huvudpriset: EKA-koden** (Read-set EKA). Samma rigg som SLABS-sniffen.

## Rigg (som SLABS)
- ESP32-tapp (RX-only, GPIO16) på pin 7 via Y-kabel; reference toolen på andra grenen.
- Mac: `python3 tools/esp32_read.py /dev/cu.usbserial-0001 logs/bcu.log`
- Jag tittar live på `logs/bcu.log`. Skriv **markör + Enter** före varje moment.

## BCU-egenheter att veta
- **BCU = SLOW init (5-baud):** själva adressen syns INTE i UART-strömmen (bit-bang =
  `00`). **Men post-init-sessionen** (EKA-läsning, felkoder, inputs) går på normal baud
  och **fångas rent** — det är det viktiga.
- **Tändningsläge:** metoden säger **läge II** för EKA. Men BCU är permanent matad och
  svarar ofta med tändning AV; du minns en "av → init → på"-sekvens. **Prova och notera
  vad som funkar** (skriv markörer med tändningsläget).

## ★ HUVUDMÅL — EKA-koden (LÅGRISK, ren läsning)
1. [ ] Markör `bcu connect (tandning II)` → välj **Valeo Body Control Unit** i reference toolen.
2. [ ] Markör `read eka` → **Read-set EKA** → ENT. Koden (4 siffror) visas.
3. [ ] **NOTERA de 4 siffrorna** + skriv dem som markör, t.ex. `eka visar 4-7-1-9`.
   → **Perfekt ground-truth:** då hittar vi exakt vilka bytes = EKA (som VIN-tricket).
4. [ ] ⛔ **Tryck INTE MOD** (skriv inte över EKA) om du inte medvetet vill ändra den.

## Övriga LÄS-funktioner (ofarliga, kör om tid finns — markör före varje)
- [ ] `bcu faults` — läs felkoder
- [ ] `bcu inputs` — lås/CDL, tändningslägen 1/2/3, fönster, backljus, mileage…
- [ ] `bcu settings` — ljus/fönster/marknadskonfig (bara LÄS)

## ⛔ RÖR ALDRIG
- Nyckel-/transponderprogrammering (brick-zon).
- Skriv över EKA (om du inte medvetet sätter känt värde).
- Larm-/immobiliser-skrivningar.
- Vår tapp sänder aldrig (RX-only) — men på reference toolen: **bara läsa**.

## Efter loggning — capture-mål
- **BCU init-typ + keybytes** (post-init syns; adress ~0x40 känd).
- **EKA-läs-tjänst + kod-bytesen** (korsa mot de noterade 4 siffrorna).
- **Fault-läs-tjänst**, **input-LID:ar**.
- → sedan `d2diag.bcu`-lager med `read_eka()` (+ ev. `set_eka()` bakom spärr).

## Markör-tips
Skriv kort + tändningsläge: `bcu connect II` · `read eka` · `eka=4-7-1-9` · `faults` ·
`inputs` · `settings`. En markör precis före varje klick räcker.
