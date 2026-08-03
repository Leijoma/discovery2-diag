# Wabco SLABS (Discovery 2) — diagnostikkapabiliteter

Funktionell referens för det framtida **SLABS-lagret** i d2diag. Beskriver *vad*
Wabco SLABS-styrdonet exponerar diagnostiskt (signaler, förväntade värden,
tester) — **inte** råprotokollet (adress/init/tjänstebytes är fortfarande okänt,
se nedan).

**Källa:** a commercial vendor / reference tool modul **SM016 "WABCO SLABS"** (kapabilitets-
beskrivning), samt reference tool "Wabco SLABS – System Overview". Faktauppgifter
(signalnamn, spänningsintervall, tillstånd) sammanställda här i egen struktur;
ingen text kopierad ordagrant.

## Om styrdonet
- Kombinerat styrdon: **ABS + SLS + EBD + ETC + HDC + EAS** i en enhet, delade
  givare/ventiler. Sitter bakom handskfacket. Finns på **alla** D2 (luft- eller
  spiralfjädrad — `Suspension type`-flaggan avgör).
- Internt uppdelat i **moduler** (Diagnostic, Measurement, ABS, EBD, HDC, Traction),
  var och en med egen referenskod — kan ändras oberoende.
- **Comms dör >8 km/h** (alla fyra hjul) — designat, går ej runt. **All läsning
  stillastående.** Nås via OBD-uttaget (pin 7, delad K-line — se plattformens
  övriga noteringar).

## Kapabiliteter (fem grupper)

### 1. Läs felkoder
Läser SLABS felminne. Fel listas som **Current** eller **Intermittent** + **antal
gånger detekterat**. Upp till **47 feltyper**. ⇒ Idealiskt för intermittent
"tre amigos": räknaren finns kvar även efter omstart.

### 2. Radera felkoder
Rensar felminnet.

### 3. Inställningar (läs/skriv identitet + konfiguration)
Identitet (läs): Factory code, Bar code, Product number/date, modulkoder
(Channel/Safety/Diagnostic/Measurement/ABS/EBD/HDC/Traction), **VIN**, Engine type
(endast med motor igång), Gearbox (endast igång).
Status/konfig (vissa skrivbara): **ECU condition** (new-born/used, ej reversibel),
Test status, **Transport mode**, **Calibrated**, **Suspension type** (air/coil —
enda skillnaden mot en ren ABS-ECU), **Left/Right current height** (0–255, ~1,4 mm
per steg), Left/Right stored height (skriv-bara; läses som N/A).

### 4. Inputs — livedata (realtid)
**Spänningar** (stillastående OK):

| Signal | Förväntat (aktiv / vilande) |
|---|---|
| Hjulhastighetsgivare (FR/FL/RR/RL) — DC-nivå | **2,0–2,4 V** |
| Inlopps-/utloppsventil | 2,8–3,6 V / 0–0,5 V |
| Pump monitor | 2,9–3,8 V / 0–0,2 V |
| Pump relay | 2,8–3,6 V / 0–0,5 V |
| HDC brake-relä | 2,8–3,6 V / 0–0,5 V |
| Ground reference | −0,5…+1 V |
| Bakre höjdgivare-matning (V/H) | 4,7–5,6 V |
| L/H bakre luftfjädringsventil, kompressorrelä, avgasventil | (uppmätt) |
| Internal ECU supply, Battery voltage | (uppmätt) |

**Switches / hastighet / värden** (ändras vid rörelse; comms dör >8 km/h):
höjdgivarvärde V/H (~1,4 mm/steg), hjulhastighet per hjul (kan ej mäta <1,8 km/h),
brytare (off-road, HDC, neutral [aldrig GND på manuell], difflås, back, låg­växel,
dörr), **RPM** (kan ej mäta <300 → visa 0), Throttle angle (grader), Engine torque (Nm).

Två extra tillståndssignaler med definierade lägen:
- **Shuttle** (bromshuvudcylinderns shuttle-ventiler): `OPEN CIRCUIT` (kablage/kontakt
  trasig), `BOTH OPEN` (broms släppt, HDC/ETC-styrt), `ONE CLOSED` (övergång/lätt
  broms), `BOTH CLOSED` (broms nedtryckt, ABS-styrt), `SHORT TO GROUND` (fel).
- **Plip signal** (från BCU): `GROUND` (fel), `LOWER`, `NEUTRAL`, `RAISE`, `OPEN CIRCUIT` (fel).

### 5. Outputs — ställdonstester (ON/OFF)
Instrumentlampor (via BCU): SLS, off-road, traction (TC), ABS, HDC (på/fel),
broms/EBD. **ABS-ventiler**, **SLS-ventiler**, luftfjädringskompressor, SLS-summer,
**ABS-pumprelä**, **hastighetsmätare** (simulerar 100 mph), **bromsljusrelä**.

### 6. Övriga funktioner
ABS power bleed, ABS modulator bleed, höj/sänk bakre vänster/höger hörn (corner-
ventil + inlopp/avgas), **Store heights** (spara aktuella höjder).

## Relevans för "tre amigos" (ABS/TC/HDC)
Registrets orsakslista mappar rakt på läsbar SLABS-data:
1. **Hjulhastighetsgivare** → givarspänning (2,0–2,4 V) + km/h per hjul, live.
2. **Shuttle valve-kontakt** → `Shuttle`-tillståndet direkt.
3. **SLABS-styrdon** → felkoder (Current/Intermittent + räknare) + ventil-/pump­spänningar.
Ställdonstesterna (ABS-ventiler, pumprelä) kan bekräfta misstänkt hårdvara.

## Kvarvarande lucka (för att implementera)
Råprotokollet är **inte** publikt: SLABS **diagnosadress**, **init-typ**
(fast/slow 5-baud), **baud** och **tjänstebytes** för läs/rensa/inputs/outputs.
Måste tas fram via bussavsökning (pin 7, stillastående) eller sniffning innan ett
`d2diag`-SLABS-lager kan byggas. KWP2000-lagret, den toleranta läsningen och
mönstret från Td5-lagret är återanvändbara när adress/init är kända.
