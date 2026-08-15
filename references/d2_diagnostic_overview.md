# Discovery 2 — diagnostiskt modullandskap

Översikt över D2:ans styrdon på diagnostiken, för att bredda plattformen bortom
Td5-motorn. Sammanställt ur verkstadsmanualen, community-research och reference tool/
a commercial vendor modul-guider (protokollfakta; ingen kod kopierad).

## Fysisk anslutning (BELAGT ur FABRIKSSCHEMA 2026-08-05)
**Källa:** `referens docs/d2_electricalcircuitdiagrams_2000.pdf` (Discovery II 2000MY
Electrical Circuit Diagrams, 2nd ed) — Land Rovers eget kopplingsschema. Detta
AVGÖR pin-frågan definitivt (slut på gissningar).
- **Diagnosuttag V100, enda inkopplade stift:** `C0040-4 B` (jord), `C0040-5 B`
  (jord), **`C0040-7 K` = K-LINE (enda!)**, `C0040-13 R` (signal), `C0040-16 P`
  (batteri +). **INGET pin 8. INGEN andra K-line. Ingen L-line (pin 15).**
- **K-line-splits `Y128` ("K LINE")** = passiv gemensam nod (multidrop). Ledningskod
  **K, 0.5 mm²**. Diagnosuttaget (`C0040-7`) OCH **SLABS (D163)** (`C0647-10 K`→Y128,
  även via header 0286 `C0286-17`→`C0504-5`) ligger på SAMMA splits. Övriga på Y128
  via header 0286 (K109): **ECM D131** (motor), **BCU D162** (`C0661-4`), **växellåda
  D123/EAT** (`C0193-31`), **SRS/airbag** (`C0256-9`).
  ⇒ **SLABS ÄR elektriskt på pin 7:s K-line — vår KKL når den redan.** Tystnaden är
  100 % protokoll (init/adress/tajming), INTE stift och INTE en elektrisk gateway.
- **BCU "gateway"** = på sin höjd logisk/mjukvarukoordinering; schemat visar passiv
  splits, så alla moduler hör allt ⇒ ett lånat verktygs trafik ÄR sniffbar på pin 7.
- Skiljer sig per modul: **diagnosadress, init-typ (fast/slow), tjänstebytes** —
  kvarvarande research/probe-arbete per modul (pin-frågan är STÄNGD).

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

## REFERENCE-TOOL SNIFF 2026-08-07 — SLABS = FAST INIT 0x29 (bekräftat), BCU = SLOW
Lånad **reference tool 1** (läser motor/SLABS/BCU/ABS/airbag/ACE; **ej autolåda**). Passiv
sniff av pin 7 (Y-kabel + KKL) fångade reference toolens init per modul:
- **SLABS: `81 29 F7 81 22` (FAST init, adress `0x29`) → svar `03 c1 57 8f aa`**
  (C1 57 8F, KWP2000). Reproducerbart. ⇒ **SLABS var fast init på 0x29 hela tiden**
  (pyTD5Tester-kandidaten stämde). Vårt eget fast-scan missade 0x29 pga KKL:ns orena
  init-puls — ESP32-realtidstajming bör nå den. **SLABS är alltså INTE en slow-modul.**
- **BCU: SLOW init** — reference toolens BCU-init syns bara som `00` (5-baud bit-bang, ej
  UART-läsbar). Stämmer med vårt 0x40 (slow, permanent matad, funkar tändning-av).
- Slow-init-modulerna 0x18/0x33/0x40 var alltså BCU (0x40) / OBD-generisk (0x33) / 0x18(?),
  inte SLABS.

**KKL duger EJ som passiv tapp:** lastar bussen → reference toolen kan inte hålla sessioner
(motorn svarade ej; SLABS-session bröts efter init). Vi fångar bara **init-handskakningen**,
aldrig fault-/live-tjänster; slow-init-adresser syns ej i UART. **Nästa: HÖGIMPEDANS
read-only-tapp** (ESP32 RX-gren / diskret, 47 kΩ+ serie, ingen TX på bussen) för djupfångst.

## GENOMBROTT 2026-08-05: chassimoduler svarar på 5-BAUD SLOW INIT (belagt)
`tools/slabs_hunt.py full` + `tools/verify_slow.py` mot bilen. Fast init (alla
varianter, 0x01–0xFF) var tyst utom motorn — **fel init-metod.** Med **5-baud slow
init** (ISO 9141) svarar flera moduler med **komplett, reproducerbar handskakning**
(0x55 sync + KW1 KW2 + korrekt `~address`-bekräftelse):

| Adress | KW1 KW2 | Protokoll | Verifierat |
|---|---|---|---|
| **0x18** | `08 08` | ISO 9141-2 | 3/3 komplett (~addr 0xE7 ✓) |
| **0x33** | `08 08` | ISO 9141-2 | 3/3 komplett (~addr 0xCC ✓) |
| **0x40** | `e5 8f` | KWP2000 (KW2=8F) | 2/3 komplett (~addr 0xBF ✓) |

**IDENTITET (research 2026-08-05, community + strömdomän) — omtolkar 0x33:**
- **0x33 = generisk OBD-II** (INTE en chassimodul). `0x33` är *standard*-5-baud-OBD-II-
  adressen (ISO 9141-2), och `55 08 08` är textbok-ISO9141-2-svaret. ⇒ Detta är
  **Td5-motorns OBD-II-sida** (samma ECM som svarar fast init på 0x13). Community:
  "cheap devices only read engine codes" — 0x33 är just den generiska motoringången.
- **0x40 = trolig BCU (Valeo).** KWP2000 + svarar med nyckel HELT AV = permanent
  batterimatad; enda D2-modulen som är det (larm/immobiliser). Medel-hög konfidens.
- **0x18 = oklart.** ISO9141-2 (KW 08 08) som 0x33, tändningsmatat. Antingen en riktig
  proprietär modul (SLABS/EAT/SRS?) ELLER motorns OBD-sida på en andra adress. Låg konf.
- **SLABS/EAT/SRS ännu EJ lokaliserade.** VIKTIGT: slow-init-scanet testade bara en
  KANDIDATLISTA (0x08/14/18/28/29/33/34/38/40/44/50), inte hela 0x01–0xFF. SLABS kan
  ligga på en oskannad slow-adress. **Nästa biltest: `tools/slow_sweep.py <port>`** —
  uttömmande slow-svep 0x01–0xFF med handskakningsklassning (KOMPLETT/SYNC/tyst) +
  auto-omverifiering (3×/8 s) + KW/protokoll-tolkning. Ett kommando, ~13 min, tändning på.
Källor: discoii.wordpress OBDII, a commercial vendor SM016, reference tool Valeo-BCU/Wabco-guider,
obd-cable ISO9141-5-baud (0x33 std-adress, 55 08 08=ISO9141 / 55 8F..=KWP).

**Strömdomän-fingeravtryck (3 nyckellägen, 2026-08-05):** 0x40 svarar **även i läge 0
(nyckel helt av)** = **permanent batterimatad** → **BCU (Valeo)** i praktiken bekräftad
(alltid live för larm/immobiliser; flakig i läge 0 = väcks ur sleep). 0x18 & 0x33 tysta
i läge 0 OCH läge 1, svarar bara med **tändning på** = tändningsmatade → **SLABS/EAT/SRS
m.fl.** ⇒ **0x40/BCU kan testas/sniffas helt utan nyckel** (enklast, + KWP2000 som motorn
→ bästa modulen att knäcka post-init-formatet på först). SLABS kräver läge 2.

**Session-lås bekräftar äkthet:** efter en lyckad slow init går modulen in i session
och tystnar på nya init tills timeout (~sek) — därför krävs **≥8 s mellan försök**.
Fast repeat (2 s) ger tyst #2/#3; 8 s ger 3/3. En artefakt vore inte stateful så.
0x18 & 0x33 delar KW `08 08` (kanske samma modul på två adresser). 0x40 = eget
KWP2000 (KW2=0x8F, som motorns `57 8F`) ⇒ **vår KWP2000-stack bör nå 0x40 efter slow
init.** Motorn 0x13 = fast init (undantaget). **Kvar:** identifiera vilka moduler
(SLABS/BCU/EAT/SRS?) via post-init-request (0x40 KWP2000 först), sedan läs-DTC/data.
Fast-init-hypotesen för SLABS (forum) motbevisad för dessa adresser.

## Utökat SLABS-jakttest (`tools/slabs_hunt.py`) — sista försöket på pin 7
Ett kommando kör hela den kvarvarande pin-7-matrisen i EN körning med gemensam,
tidsstämplad logg (`logs/slabs_hunt-<stamp>.log`). Faser:
1. **Länkkoll** — fast init mot motorn (0x13), förväntar `C1 57 8F`. Bevisar att
   kabel/OBD/jord/tajming är OK → tystnad från SLABS blir ett *svar*, inte en trasig länk.
2. **Passiv sniff** ~20 s RX-only vid nyckel-på (BCU=gateway kan polla moduler).
3. **Aktiv matris** — `fast-f1`, `func-f1`, `func-f7` över 0x01–0xFF + `slow` mot
   kandidatadresser. Söker C1/7F resp. 0x55. Motorn 0x13 hoppas alltid över.

Körning (stillastående, tändning på):
```
PYTHONPATH=src python3 tools/slabs_hunt.py <port> full     # ~15 min, hela matrisen
PYTHONPATH=src python3 tools/slabs_hunt.py <port> quick    # ~3 min, bara kandidater
```
**Kreativ variabel:** kör en gång **motor AV** och en gång **motor på tomgång**
(SLABS/EAS/SLS aktiva → modulen kan vara vaken annorlunda). Total tystnad i BÅDA
→ starkt stöd för pin-8-hypotesen. Loggas per körning för jämförelse.

**Nuanserad slutsats 2026-08-04:** D2-specifika källor säger samstämmigt att pin 7
delas av allt (SLABS/ACE/trans/BCU) med **BCU som gateway**. Pin-8 (BMW-konvention)
nedgraderad men ej utesluten. Ledande förklaring till tystnaden: **BCU-gatewayen
dirigerar inte vår init till SLABS**. Avgör med (1) fysisk pin-koll i uttaget,
(2) **sniffa ett lånat verktyg** (nästa steg) → visar exakt hur det når BCU→SLABS.

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
