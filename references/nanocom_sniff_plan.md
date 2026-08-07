# reference tool-helg — sniff-testplan & funktions-TODO (Discovery 2)

Mål: medan reference toolen (lånad) pratar med bilens moduler **sniffar vi passivt pin 7**
och fångar det vi inte kunde gissa: **exakt init, adress, keybytes, header-format,
tjänstebytes, felstruktur, ev. seed/key** — per modul. Sedan kan vi bygga egna
d2diag-lager (SLABS/BCU/EAT) på riktig trafik.

Källor: reference tool Evolution User Guide (v1.3), reference tool Wabco-SLABS- & Valeo-BCU-guider.

---

## ⚠️ SÄKERHET — läs först

- **Bricking är verkligt — men BARA vid skrivning/programmering.** Läsning +
  passiv sniff = säkert.
- **Vår regel: bara LÄSA på reference toolen. Inga writes, ingen programmering.**
- **BCU immobiliser/EKA/nyckelprogrammering = absolut förbjudet** — kan låsa bilen.
  Guiden: *"A LOCKED BCU CANNOT BE UNLOCKED BY DIAGNOSTIC METHODS."*
- **SRS/Airbag: läs ENDAST felkoder.** Kör aldrig utgångar/tester (pyroteknik).
- **Avbryt aldrig reference toolen mitt i en operation** (ström/komm) → korrupt minne.
- **Vår sniffer MÅSTE vara RX-only.** Sänder den kan den störa/skada. `sniff.py`
  läser bara; kör inget som sänder. (ESP32+L9637D i ren RX är ännu säkrare.)
- Om reference toolen fryser: undvik att spamma knappar (kan krascha/boota om den).

---

## FAS 0 — Rigg & kontroll (innan reference toolen kopplas)

- [ ] **Y-kabel, multimeter:** vår gren har **pin 7 (K), pin 4+5 (jord), pin 16 (12V)**
      genomkopplade (KKL:ns transceiver behöver 12V+jord). Kontinuitet socket↔grenar.
- [ ] Sniffer på vår gren, **RX-only**. reference tool på andra grenen.
- [ ] Stillastående, **tändning på, motor av**. (SLABS tappar comms >8–20 km/h.)
- [ ] Testa att `sniff.py` loggar tidsstämplat.

## FAS 1 — Validera riggen på KÄND modul (motorn)

- [ ] Ny logg `sniff_engine.log`. reference tool → **Td5 Engine (EDC)** → Read faults + live.
- [ ] Bekräfta i loggen: `81 13 F7 81`, `C1 57 8F`, ev. `27 01→seed`, `21 xx`.
      Matchar vår kända Td5-kunskap ⇒ **rigg + annotering bevisat rätt.**

---

## FAS 2 — De okända, EN modul i taget

**Prioritet:** SLABS → BCU (läs) → EAT → ACE → SRS.
**För varje funktion:** [ ] ny/fortsatt logg · [ ] notera **tid + reference tool-åtgärd**
(korrelation!) · [ ] kör · [ ] verifiera att bytes kom med.
**Ordning per modul:** anslut (→init/adress/keybytes) → **felkod-cykel (läs+rensa)** →
läs inputs → läs settings. Övriga skriv-funktioner hoppas (se ⚠️).

### ★ Felkod-cykel — läs OCH rensa (fånga BÅDA tjänsterna)
Vi vill lära oss **både läs- och rensa-tjänsten** (clear = en *säker* write; behövs
för att bygga `clear_faults`). Gör för varje modul, och **notera tid+åtgärd för varje
steg** så bytes kan paras ihop:
1. [ ] **Läs felkoder** → fånga läs-tjänst + svarsstruktur (Current/Intermittent/räknare).
2. [ ] **Rensa felkoder** → fånga **clear-tjänsten** (jfr Td5 `14` / `31 DD`).
3. [ ] **Läs igen** → fånga hur ett **tomt/rensat** svar ser ut (viktig referens).
   (Verkligt aktuella fel kan komma tillbaka direkt — det är också nyttig info.)

### ★★ (Valfritt, HÖGT värde) Framkalla ett KÄNT fel — ground-truth för avkodaren
För att mappa **råbyte/-index ↔ felnummer** exakt (annars gissar vi): koppla ur en
**känd, ofarlig, reversibel** givare och läs → ett *specifikt* fel dyker upp vars
nummer vi vet ur [slabs_fault_codes.md](slabs_fault_codes.md), så vi ser dess råa
representation. Bäst kandidat på SLABS: **en hjulhastighetsgivare-kontakt** →
ger t.ex. "Sensor Electric Fail" (064–067) för just det hjulet. Sekvens:
läs (tomt) → dra ur EN givare → läs (fel N syns) → **återanslut** → rensa → läs (tomt).
Då har vi en exakt ankarpunkt; resten av den systematiska listan faller på plats.
⚠️ Bara ofarliga/reversibla givare (hjulhastighet, höjd). **Aldrig airbag/pyro.**
Stillastående, tändning på. Notera exakt vilken kontakt + tidsstämpel.

### 🔵 SLABS (Wabco, ABS + luftfjädring) — PRIO 1 (tre amigos)
| # | Funktion | Typ | Vad vi fångar |
|---|---|---|---|
| [ ] | **Anslut** till SLABS | — | init (slow/fast?), adress, keybytes |
| [ ] | **Read Fault Codes** (Current/Intermittent + räknare, 47 typer) | READ | fault-läs-tjänst + svarsstruktur |
| [ ] | **Clear Fault Codes** | (säker write) | clear-tjänst (jfr `14`/`31 DD`) |
| [ ] | **Inputs — ABS** (hjulhastighet FR/FL/RR/RL, 2.0–2.4 V) | READ | live-data-tjänst (`21 xx`?) |
| [ ] | **Inputs — SLS** (höjdgivare, 0–255 ≈ 1.4 mm/steg) | READ | fler LID:ar |
| [ ] | **Inputs — Switch** | READ | switch-block |
| [ ] | **Settings (LÄS)** — Test status, ECU calibrated, Transport mode, Suspension type, current heights | READ | settings-läs-tjänst |
| [ ] | ⚠️ Store Target Heights / Suspension type / Test status | **WRITE** | **HOPPA** (ändrar kalibrering) |
| [ ] | (valfritt) **Outputs** — pump, ventiler, lampor, kompressor | write/aktiverar | output-control (`2F`/`31`); stillastående, försiktigt |

### 🟢 Valeo BCU — PRIO 2 · **LÄS ENDAST** (funkar även med tändning av)
| # | Funktion | Typ | Vad vi fångar |
|---|---|---|---|
| [ ] | **Anslut** till BCU | — | bekräfta adress 0x40 + KWP2000 (vår hypotes) |
| [ ] | **Read Fault Codes** | READ | fault-tjänst |
| [ ] | **Read Inputs** (lås/CDL, tändningsläge 1/2/3, fönster, backljus, diff-lås, mileage…) | READ | input-block |
| [ ] | **Settings (LÄS)** — ljus/fönster/säten/marknadskonfig | READ | settings-läs |
| [ ] | ⛔ **Immobiliser / EKA / nyckelprogrammering / alarm** | **WRITE** | **RÖR ALDRIG** — brick/låser bilen |

### 🟡 EAT — Automatlåda (ZF4HP22/24) — PRIO 3
| # | Funktion | Typ | Vad vi fångar |
|---|---|---|---|
| [ ] | **Anslut** till autolådan | — | init/adress/keybytes |
| [ ] | **Read Fault Codes** | READ | fault-tjänst |
| [ ] | **Read Inputs** (oljetemp, växelläge, varvtal…) | READ | live-data |
| [ ] | **Settings (LÄS)** | READ | settings-läs |

### 🟠 ACE (Active Cornering Enhancement) — PRIO 4
| # | Funktion | Typ | |
|---|---|---|---|
| [ ] | Anslut · Read faults · Inputs (tryck/ventiler) · Settings (läs) | READ | init/adress + tjänster |

### 🔴 SRS / Airbag — PRIO 5 · **ENDAST FELKODER**
| # | Funktion | Typ | |
|---|---|---|---|
| [ ] | Anslut · **Read Fault Codes** | READ | init/adress + fault-tjänst |
| [ ] | ⛔ Outputs / ställdonstester | **WRITE** | **ALDRIG** (pyroteknik) |

---

## FAS 3 — Korrelation (gör loggen läsbar)
Notera **tid + exakt reference tool-åtgärd** för varje steg ("14:03 SLABS läs felkoder").
Utan det blir bytes↔funktion svårt efteråt. (Alternativ: markör-sniffern.)

## FAS 4 — Avsluta
- [ ] Spara alla loggar namngivna per modul.
- [ ] Notera **reference toolens firmware-version**.
- [ ] Inga writes gjorda (utom ev. Clear faults).

---

## Vad vi vill ha ut per modul (capture-mål)
1. **Init** — slow (5-baud) eller fast, och **exakt adress** (löser SLABS-frågan).
2. **Keybytes** → protokoll (ISO9141 vs KWP2000).
3. **Header-format** post-init (det vi INTE kunde gissa).
4. **Fault-läs-tjänst** + svarsstruktur (bit/räknare-layout).
5. **Live-data-tjänst** (`21 xx`-motsvarighet) + vilka LID:ar ger vilka signaler.
6. **Ev. security** (seed/key) → vi kan bygga keygen som för Td5.

> Efter helgen: mata loggarna genom `d2diag/sniff.py` (`describe`) för annotering,
> och bygg SLABS/BCU/EAT-lager på verklig trafik.
