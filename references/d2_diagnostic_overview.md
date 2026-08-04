# Discovery 2 — diagnostiskt modullandskap

Översikt över D2:ans styrdon på diagnostiken, för att bredda plattformen bortom
Td5-motorn. Sammanställt ur verkstadsmanualen, community-research och reference tool/
a commercial vendor modul-guider (protokollfakta; ingen kod kopierad).

## Fysisk anslutning (BELAGT)
- **En enda K-line på OBD-stift 7** (ISO 9141-2 / KWP2000). Ingen L-line (pin 15).
  Anslutna stift: 16 (batteri), 7 (K), 4 (chassijord), 5 (signaljord), 13 (valfri).
- **Delad buss:** motor, SLABS, ACE, BCU m.fl. hänger på samma K-line; **BCU
  fungerar som gateway**. Att dra ur ett styrdon kan störa hela länken.
  ⇒ **Vår befintliga kabel (pin 7) når alla moduler** — det som skiljer dem är
  adress + init + tjänster, inte stift.
- Skiljer sig per modul: **diagnosadress, init-typ (fast/slow), tjänstebytes** —
  detta är kvarvarande research/probe-arbete per modul.

## Moduler att kartlägga
| Modul | Vad | Källor / status |
|---|---|---|
| **Td5 EDC** (motor) | Adress 0x13, fast init, seed/key. **KLART** i d2diag. | Ekaitza + reference tool (felkarta korsvaliderad) |
| **Wabco SLABS** | ABS/SLS/EBD/ETC/HDC/EAS. 47 feltyper, Current/Intermittent + räknare. | `wabco_slabs_capabilities.md`. **FAST init** (ej slow!); kandidatadress **0x29** → `probe_slabs.py` |
| **Valeo BCU** | Centralelektronik + **immobiliser/larm/EKA/nyckelprogrammering**. | `valeo_bcu_capabilities.md`. Adress/init okänt |
| **SRS/airbag** | Krockkuddar. | Ej kartlagt |
| **ACE** | Active Cornering Enhancement (krängningsstyrning). | Egen K-line-diagnostikstift; ej kartlagt |
| **HEVAC** | Klimat. | Ej kartlagt |
| **EAT** | Automatlåda — **bilen är AUTOMAT**, så modulen är relevant. | Ej kartlagt |

## Resurs: reference tool/a commercial vendor modul-guider (funktionella kapabiliteter)
a commercial vendor publicerar per-modul-guider (PDF) som beskriver *vad* varje
modul exponerar (inputs/settings/outputs/fault codes) — utmärkt för att bygga
respektive lager. Extraherbara med `pdftotext`. Kända URL:er:
- BCU: `reference tool-diagnostics.com/uploads/downloads/Discovery II Valeo BCU ECU Guide.pdf`
- SLABS: `reference tool-diagnostics.com/downloads/preview/wabco-slabs`
- Hjälpsidor per modul: `a commercial vendor/help/SMxxx.html` (SLABS = SM016).
Fler moduler (SRS/HEVAC/ACE/EAT) har troligen motsvarande guider på samma
download-sökväg — värt att prova när vi tar oss an dem.

## SLABS felkodsformat (samma som Td5!)
Community-koder anges som **(X,Y)** eller **X-Y** — samma bit-per-fel-indexering
som Td5:ans `21 3B` (X = byte-offset+1, Y = bit+1). Kända exempel:
- `(1,1)` at start of sequence
- `(2,12)…(2,15)` air gap: RH front / LH rear / LH front / RH rear (hjulhastighetsgivare)
- `(15,4)` front left outlet valve open circuit
- front right outlet valve short to ground; shuttle valve switch electrical failure
Detta antyder att SLABS-felminnet kan avkodas med **samma teknik som Td5**
(offset*8+bit → feltext) när vi väl har adress/init och kan läsa blocket. Full
lista (47 typer) finns i Nancom-firmware men är inte publikt dumpad — **läses ut
när vi väl kopplar upp mot SLABS.**

## Biltest 2026-08-04 (fler init-varianter) — SLABS ligger på pin 7
`probe_slabs.py` + `probe_addresses.py 40 FF` + F1-varianter mot bilen (motorn C1 felfri):
- **0x29/0x34 (F7 fysisk + F1 fysisk + funktionell): tyst.**
- **Hela 0x01–0xFF fysisk fast init F7: tyst** utom 0x13.
- Motorns kontroll gav `03 c1 57 8f aa` varje gång → uppkoppling/tajming utmärkt.

**BELÄGG (LR OBD-pinout + community): pin 7:s K-line på D2 delas av ECM, ABS,
SLABS, HVAC, farthållare, instrument** — INGEN separat kroppssystem-K-line (pin 15
= L-line, knappt använd, bara ECM). reference tools **Blue-lead** når alla; NCOM13/NCOM15
= mjukvarulås, ej olika kablar. ⇒ **SLABS ÄR nåbar på pin 7 (vår tråd) — det är
protokoll/adress, inte stift.** (Tidigare "separat stift"-hypotes förkastad.)

**Kvar att prova (multi-läges, `tools/probe_scan.py`):** fast **F1** (hela 0x01–0xFF),
**funktionell (C1)** F1/F7, samt **slow init** (nu rättad 8N1 — SLABS kan trots
forumet använda ISO 9141 0,4 kb/s). Kreativt: **passiv sniff vid nyckel-på** (BCU=
gateway kan väcka/pinga moduler → adresser utan att gissa init). Total tystnad hittills
tyder ändå på ovanlig init/adress → **sniffa ett lånat verktyg** är fortsatt säkraste vägen.

## Bussavsökning 2026-08-03 (korrigerad 2026-08-04)
`tools/probe_addresses.py` mot bilen (stillastående, tändning på):
- **Endast 0x13 (motorn) svarar på fysisk fast init** (`81 <addr> F7 81`, positivt C1).
- Med motorsessionen dormant + 0x13 orörd: ingen adress **0x01–0x3F** svarade.
- (Obs: en ÖPPEN motorsession generalRejectar alla adresser och maskerar bussen —
  motorn måste vara dormant, och 0x13 får ej adresseras.)

**Korrekt (mildrad) slutsats:** *ingen annan modul svarade på just **fysisk fast
init med testare F7 i 0x01–0x3F** under denna skanning.* Det **bevisar inte** slow
init. **Motbevis (LR-forum + pyTD5Tester):** SLABS använder **KWP2000 fast init** —
någon läste hjulhastighet/switchar + styrde utgångar den vägen. Konkret kandidat:
**`81 29 F7 81 22`** (fysisk 0x29, F7) och funktionell **`C1 34 F1 81 67`** (0x34, F1).
Skanningen missade dem (utanför 0x01–0x3F, annan testaradress, ev. funktionell init).
Läs-DTC via standardtjänsten ger "invalid function" på SLABS; **clear (0x14) fungerar**
→ felläsning sker via icke-standardtjänst, troligen `21 xx` (som Td5).
**Nästa test:** `tools/probe_slabs.py` (riktat mot 0x29/0x34, lång tystnad, ≥5 s mellan).
Slow init behövs alltså troligen INTE för SLABS (men `slow_init` finns kvar, buggen
med 7→8 databitar rättad 2026-08-04, för ev. andra moduler).

## Sniffning — bästa vägen till okända protokoll
K-line är en tråd, halvduplex → en **passiv RX-lyssnare fångar hela samtalet**
(både verktygets frågor och ECU:ns svar). Med ett lånat verktyg (reference tool/a commercial tool/
a commercial tool) som läser SLABS får vi adress, init, tjänstebytes och felstruktur ur
verklig trafik — precis så Ekaitzas `Sniffing/*.log` (och därmed vår Td5-kunskap)
skapades.
- **Inkoppling:** OBD-splitter (piggyback) — lånat verktyg i ena grenen, vår
  lyssnare i andra. Kräver att splittern kopplar igenom **pin 7** (K-line).
- **Lyssnare:** ESP32 + L9637D i ren RX (bäst), eller KKL enbart RX. **Bara RX —
  sänd aldrig**, annars krockar man med verktyget.
- **Verktyg:** `tools/sniff.py` (RX-only, tidsstämplar, ramar på tystnadsgap,
  annoterar tjänster). Kärna i `d2diag/sniff.py` (`frame_by_gaps`, `describe`).
- 5-baud-adressen syns inte i UART-strömmen (200 ms/bit) — ta den med `probe_slow`
  eller sampla linjenivån; men tjänsterna/felstrukturen (det svåra) fås ur sniffen.

## Nästa steg för att nå en ny modul (mönster)
1. **Prova fast init först** (D2 använder mest fast init): riktade StartCommunication
   mot kandidatadresser — för SLABS `tools/probe_slabs.py` (0x29/0x34). Slow init
   (`SerialTransport.slow_init`, nu 8N1) är fallback för moduler som kräver det.
2. **Tjänster:** identifiera read-inputs/läs-DTC/clear. OBS: standard-läs-DTC kan ge
   "invalid function" (som SLABS) → prova `21 xx` ReadDataByLocalIdentifier (Td5-mönstret).
3. **Tunt modul-lager** ovanpå det generiska KWP2000-lagret (återanvänd Td5-mönstret).
