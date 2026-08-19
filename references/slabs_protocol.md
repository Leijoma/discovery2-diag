# Wabco SLABS — komplett K-line-protokoll (sniffat från reference tool 1)

Fångat 2026-08-07 via passiv ESP32-tapp (RX-only, GPIO16) på pin 7, medan en lånad
**reference tool 1** körde hela funktionsuppsättningen. Rå logg + markörer:
`logs/session.log` (avkodas med `tools/decode_session.py`). Detta är **belagt ur
verklig trafik**, inte gissat.

## Grundläggande
- **Adress `0x29`, FAST init:** `81 29 F7 81 22` → svar `C1 57 8F` (KWP2000, KW2=8F).
  ✅ **Init fungerar sedan 2026-08-19** — se "Init-pulsen" nedan. Att det tidigare
  krävdes många försök var VÅRT fel (TiniH ~32 ms i stället för 25), inte modulens.
- **Session:** oadresserade, längd-prefixade ramar `<len> <SID> <data…> <cs>`
  (checksumma = byte-summa & 0xFF), samma stil som Td5-sessionen.
- **Keepalive:** `01 3E` → `7E` (TesterPresent), ~1 s. **OBS: bar `3E` utan
  sub-byte** (ram `01 3e 3f`). `3E 01` får inget svar och river sessionen.
- Kräver **tändning PÅ** (tändningsmatad modul). Comms dör >8–20 km/h.

### ⚠️ SLABS måste pollas LÄTT (bevisat 2026-08-07)
Reference tool körde ~**1 Hz keepalive + enstaka läsningar** — inte kontinuerlig
block-pollning. Vår drivare måste göra likadant:
- **Läs få LID:er, sällan.** Dashboardens `SlabsDataSource.poll` läser bara
  höjder (`21 54`). En tidigare store-driven block-läsning av 5 LID:er + felkoder i
  **varje** 0.5 s-cykel (~7× busstrafiken) kopplade upp men **dödade sessionen
  efter ~15 s**.
- **TAKTEN är lika viktig som antalet LID:er (bilen 2026-08-18).** Att bara läsa
  `21 54` räckte inte: med serverns 0,5 s-cykel blev det `3E` + `21 54` = **4
  ramar/s**, medan reference tool körde ~1 Hz (keepalive `01 3e 3f` var ~1048:e ms
  i sniffen). Sessionen dog efter 21 s (uppkopplad 20:54:28, död 20:54:49).
  Trafiken är därför strypt på **klockan, inte pollcykeln**: `_SLABS_BUS_PERIOD =
  1.0 s` och felkoder på egen kadens `_SLABS_FAULT_PERIOD = 30 s`. Extra pollar
  returnerar cachade värden utan att röra bussen.
### ⚠️ Init kräver en TYST PERIOD — inte fler försök (mätt 2026-08-18)
Alla reference tool-sniffar mättes om (`slabs_session_20260807`,
`td5_slabs_session_20260808`, `faultread-20260809-4`). Tiden utan trafik mot
modulen före varje initförsök:

| tyst innan | resultat |
|---|---|
| (sessionsstart) | inget svar |
| 24.9 s · 26.5 s · 27.8 s · 28.0 s · 41.0 s · 51.5 s | **C1 varje gång** |
| 59.0 s | inget svar (undantag) |

**Verktyget gjorde ALDRIG ett snabbt omförsök** — varje lyckad init kom på
*första* försöket efter tiotals sekunders tystnad. Modulen behöver alltså den
tysta perioden för att släppa sin länk, och varje init vi skickar under den
nollställer väntan. Att hamra är aktivt skadligt: det var precis det som höll oss
ute i ~2 min 2026-08-18 (och tolkningen "flera försök är normalt" i den här filen
var en feltolkning av samma sniff).

- **`establish`: `idle=0.3 s`, `attempts=3`, `retry_sleep=28 s`.** Den långa pausen
  behövs sannolikt inte längre — den infördes när init misslyckades av
  timing-skäl. Sänk den gärna och mät (`tools/slabs_probe.py --quiet 5` ger numera
  träff på första eller andra försöket).
- Bilen 2026-08-18 bekräftade den andra halvan: väl uppkopplad satt SLABS
  **stabilt i 2 min 25 s** med data (4 signaler, ingen reconnect). Den lätta
  pollen håller — problemet var bara att komma in.
- **Delad K-line-buss:** ett `7F 81 10` (generalReject) på StartCommunication =
  en session är redan öppen — **och den kommer från en ANNAN modul**. Belagt i
  sniffen 2026-08-08 (`td5_slabs_session`, t=403982): TD5:s keepalive `02 3e 01 41`
  2,9 s tidigare, sedan svarar SLABS `C1 57 8F` **och** TD5 `03 7f 81 10 13` på
  samma init — båda i samma burst. Reference tool struntade i rejecten och använde C1.
  Vår toleranta init gör likadant (söker C1 i bursten), så en reject i sig är inte
  fatal; problemet är när SLABS inte svarar alls. Vanlig orsak: en kvarlämnad **TD5-session**
  (StartDiagnosticSession + SecurityAccess) efter modulbyte.
  **Åtgärdat i kod:** `EcuSession.release()` = StopDiagnosticSession (`20` → `60`)
  + close, och den anropas vid modulbyte (`Td5DataSource.disconnect`,
  `_select`/`_set_mode` i webbservern) och mellan modulerna i `faultscan`. Bara
  `close()` räcker inte — ECU:n håller sessionen tills den timeoutar av sig själv.
  Moduler utan session (SLABS, Airbag) har `_has_session = False` → no-op.
  Kör ändå inte fault-watch som växlar moduler snabbt.
- **StopCommunication `82` → `C2` (belagt i bilen 2026-08-18).** Det räckte INTE
  att stänga TD5-sessionen. Två teardowns finns och de är olika saker:
  `20` avslutar en *diagnostiksession* (bara Td5), `82` river den
  *kommunikationslänk* som fast init upprättade — och den har varje modul.
  Bevis: en **helt ny process** med `--slabs` (ingen TD5 inblandad, SLABS som
  första modul någonsin i processen) fick `7F 81 10` på allra första
  initförsöket: `81 29 f7 81 22 03 7f 81 10 13`. Länken överlever alltså att
  vår process dör. Åtgärd i kod: `EcuSession.release()` skickar `20` (om modulen
  har session) + **alltid `82`**, och `_establish` skickar ett best-effort `82`
  före *varje* initförsök för att riva en kvarlämnad länk.
  Felvägar (tom läsning, tappad kabel) går nu också via `release()` — loggen
  visade att just de lämnade länken öppen och gav ~90 s reconnect-loop.

### `1A 8A` är reference tools FÖRSTA meddelande efter C1
I varje lyckad init i sniffarna följs `C1 57 8F` av `02 1a 8a a6` → `5a 8a …`
efter ~170 ms, innan keepalive och läsningar börjar. Vi speglar det sedan
2026-08-19 och använder svaret som **kvittens på att sessionen lever**: den
toleranta initen letar bara efter ett `C1` i bursten och kan i brus ge falskt
positivt "session established" följt av noll läsningar (sett i bilen 2026-08-18).
Uteblir svaret rivs inte etableringen — det rapporteras i anslutningsloggen, så
"uppe" går att skilja från "trodde vi var uppe".

⚠️ Kvarvarande avvikelse från verktyget: vi skickar `01 82 83` (StopCommunication)
före första initförsöket. Verktyget skickar **aldrig** `82` i någon sniff — det
litar på att länken timeoutar av sig själv. Vårt `82` löste TD5:s generalReject
men är ovaliderat mot bilen.

### P4 — inter-byte-tid vid SÄNDNING (mätt, inget utslag ännu)
Första mätningen med blandad ordning (32 försök, 2026-08-19 16:03–16:07):
**P4 = 0 ms gav 1/17, P4 = 5 ms gav 2/15.** För litet för att säga något —
skillnaden är väl inom slumpen. Hypotesen lever men är obekräftad.


muki01-referensen skickar **en byte i taget med 5 ms emellan**
(`writeRawData`: `K_Serial.write(b); delay(WRITE_DELAY)`), och kommentaren citerar
ISO 14230-2:s intervall **5–20 ms** för P4. Vi har alltid skickat hela ramen i ett
enda `write()` — vid 10400 baud tar en 5-byteram då ~5 ms i stället för ~25 ms.

En strikt ECU kan vägra parsa en ram utan P4-mellanrum. Det är en bättre kandidat
än adressläget till varför reference tool kommer in på första försöket medan vi
behöver flera, och det förklarar också varför TD5 (Lucas) fungerar medan SLABS
(Wabco) är nyckfull — olika ECU:er, olika tolerans.

`KLine(write_gap=…)` och `EcuSession._write_gap` finns nu, men **är inte påslaget
för någon modul** — testa först med `tools/slabs_probe.py --write-gaps 0,5`, som
kör P4 = 0 och 5 ms som separata celler i den blandade matrisen.

### 🔑 INIT-PULSEN var hela problemet (löst 2026-08-19)
Vår TiniH — höga perioden mellan låg-pulsen och StartCommunication — var **~32 ms
i stället för ISO:s 25 ± 1**, av två skäl:

1. **UART-stoppbiten räknades inte.** Låg-pulsen är en `0x00` vid ~360 baud;
   ramen avslutas med en stoppbit som är HÖG (~2,8 ms) och `flush()` väntar tills
   den sänts. TiniH hade alltså redan börjat.
2. **`time.sleep(25 ms)` överskjuter.** Uppmätt på macOS: 25,3–32,0 ms, median 29,1.

Åtgärd: `fast_init_low()` returnerar tiden linjen redan varit hög, och `KLine`
väntar med `_precise_wait()` (spinnande klocka) i stället för `sleep` → uppmätt
**25,00 ± 0,01 ms**.

| | Träffkvot per initförsök |
|---|---|
| Före | 3/32 = **9 %** |
| Efter | 6/11 = **55 %**, och dashboarden kopplar upp på FÖRSTA försöket |

Fishers exakta test **p = 0,007**. Tre av träffarna kom på `81 29 F7 81 22` —
adressläget var aldrig problemet, och alla hypoteser om spänning, motorstatus,
tyst period och dörrar var återvändsgränder.

**Lärdomen:** TD5 (Lucas) accepterade vår felaktiga puls utan protest i månader.
SLABS (Wabco) har ett smalare toleransfönster och avslöjade felet. En modul som
är "nyckfull" medan en annan fungerar betyder inte att modulen är trasig — det
kan vara vi som ligger på kanten av specen.

⚠️ Kvar att mäta: de **fysiska** flankerna. Vi mäter bara vår mjukvarusida; tiden
från `write()` till att byten lämnar FT232:n syns inte från Python. ESP32-tappen
kan tidsstämpla flankerna om det behövs.

### W5 och P4 — implementerade, ej bevisade
- `KLine(init_idle=…)` ger garanterad buss-idle före pulsen (ISO: 300 ms). Av som
  default. Proben: `--init-idle 1000`.
- `KLine(write_gap=…)` ger P4, inter-byte-tid vid sändning (ISO 5–20 ms, muki01
  använder 5). Av som default. Mätningen 0 mot 5 ms gav inget utslag — men den
  gjordes innan P4-väntan blev exakt, så siffran mätte snarare 8–9 ms.

### Fast-init-pulsens fysiska flanker
Sniffen är RX-only och ser bara UART-data — den elektriska init-pulsen (hur länge
K-line dras låg/hög före `81 29 F7 81 22`) syns inte i något capture. Allt på
applikationsnivå är därmed belagt och implementerat, medan pulstajmingen är
gissad från ISO 14230-2 (25 ms låg + 25 ms hög). Det är också där vårt problem
sitter: reference tool kommer in på första försöket, vi behöver flera. En ESP32 i
master-läge (se `hardware/README.md`) skulle ge deterministisk pulstajming till
skillnad från USB-KKL:ns OS-timade.

### 🔑 Adressläget: funktionell init (`C1 29 F1 81`) — outnyttjat spår
Reference tool initierar **fysiskt** med testar-adress `0xF7` (`81 29 F7 81 22`),
och det är vad vi kopierat. Men två oberoende källor pekar på ett annat läge:

| Källa | Ram | SLABS |
|---|---|---|
| Vår adressjakt 2026-08-05, `func-f1` | `C1 29 F1 81 5c` | **`C1 57 8F`** ✅ |
| Vår adressjakt, `fast-f1` | `81 29 F1 81 1c` | tyst |
| Vår adressjakt, `func-f7` | `C1 29 F7 81 62` | tyst |
| muki01 (bekräftad korrekt) | `C1 33 F1 81 66` | — (funktionell broadcast) |

**MÄTT I BILEN 2026-08-19, 8 kontrollerade körningar** (`tools/slabs_probe.py`,
en variant i taget med 30 s tystnad emellan, kvittens via `1A 8A`):

| Tid | Batteri | Motor | Utfall |
|---|---|---|---|
| 13:25 | 13,66 V | igång | tyst (alla 4) |
| 13:28 | 12,11 V | av | TRÄFF → funktionell/F7 |
| 13:32 | 11,89 V | av | tyst |
| 13:36 | 11,83 V | av | tyst |
| 13:38 | 13,71 V | igång | TRÄFF → funktionell/F1 |
| 13:42 | 13,77 V | igång | TRÄFF → funktionell/F7 |
| 13:46 | 13,80 V | igång | TRÄFF → **fysisk/F7** (första försöket) |
| 13:47 | 12,28 V | av | tyst |

**Motorn igång: 3 träffar av 4. Motorn av: 1 av 4.**

**Per FÖRSÖK (25 initförsök i 8 körningar), vilket är den bättre statistiken:**

| Motor | Träffar | Andel |
|---|---|---|
| igång | 3 av 10 | 30 % |
| av | 1 av 15 | 7 % |

**Fishers exakta test: p = 0,27 — inte signifikant.** Skillnaden ser stor ut men
materialet är för litet för att utesluta slump. Simulering säger att det krävs
~50 försök per läge för 80 % chans att nå p < 0,05 om den sanna effekten är
30 % mot 7 %.

Konfidens: **KANDIDAT, inte belagt.** n=8 är för litet, intervallen överlappar
(träffar 12,11–13,80 V, missar 11,83–13,66 V) och det finns motexempel åt båda
håll — 13:25 misslyckades med motorn igång, 13:28 lyckades med motorn av. Vad vi
har är den starkaste korrelationen vi mätt, inte en fastställd orsak. Mekanismen
är helt öppen: det kan vara matningsspänning, men lika gärna att modulen är vaken
och nivåreglerar när motorn går och går i viloläge när bilen står parkerad.

**Så här blir det belagt:** ~50 försök per läge (`tools/slabs_torture.py`, blandad
ordning med loggad seed) i tre strömlägen — motorn igång / tändning med laddare /
tändning utan laddare. **Laddarläget är nyckeln:** det ger hög spänning UTAN att
motorn går och skiljer därmed spänning från motorstatus. Mät helst SLABS egen
matning på C0504 stift 1/2 samtidigt; TD5:s batterivärde är bara en proxy för vad
modulen faktiskt ser.

**Ekot bekräftat som felkälla:** de fem falska `C1` som rapporterades 13:25–13:34
försvann helt efter echo-fixen — noll i de fem körningarna därefter.

**Adressläget: funktionellt ser bättre ut, men det är inte avgjort.**
Alla probe-försök 2026-08-19 där alla varianter provades i samma tidsfönster:

| Variant | Ram | Träffar |
|---|---|---|
| funktionell/F7 | `c1 29 f7 81 62` | 4/11 |
| funktionell/F1 | `c1 29 f1 81 5c` | 2/13 |
| fysisk/F7 | `81 29 f7 81 22` | 1/14 |
| fysisk/F1 | `81 29 f1 81 1c` | 0/7 |

Funktionellt sammanlagt **6/24 (25 %)** mot fysiskt **1/21 (5 %)** — Fishers
exakta test ger p = 0,10.

✅ **Upplöst 2026-08-19 med blandad ordning:** när variantordningen slumpas per
varv försvinner skillnaden helt — funktionell/F1 1/8, funktionell/F7 1/9,
fysisk/F7 1/7, fysisk/F1 0/8. Adressläget spelar alltså **ingen** roll; den
tidigare skillnaden var positionseffekten nedan. Behåll flera varianter enbart
för att det ger flera försök.

🚨 **Siffrorna nedan är sammanblandade med försöksnumret.** Proben körde alltid
varianterna i samma ordning, så träffkvoten per position är IDENTISK med den per
variant:

| Försök nr | Träffar | | Variant (alltid i denna ordning) | Träffar |
|---|---|---|---|---|
| 1 | 1/14 | | fysisk/F7 | 1/14 |
| 2 | 2/13 | | funktionell/F1 | 2/13 |
| 3 | 4/11 | | funktionell/F7 | 4/11 |
| 4 | 0/7 | | fysisk/F1 | 0/7 |

Det går alltså inte att skilja "funktionellt är bättre" från "andra/tredje
försöket är bättre" — t.ex. att den första init-pulsen väcker modulen och nästa
kommer fram. `tools/slabs_probe.py` blandar därför variantordningen per varv
(``--order shuffle``, seed loggas). Först med blandad ordning går frågan att
avgöra.

⚠️ **Fällan vi gick i:** ett tortyrpass låstes till enbart `fysisk/F7` och gav
0 träffar på 50 försök. Det såg ut som att modulen slutat svara helt, men vi hade
bara slutat skicka de ramar som brukade fungera. Lås aldrig experimentet till en
variant innan frågan är avgjord.

**Arbetsregel (inte en fastställd sanning): kör motorn när du pratar med SLABS.**
Den ger bäst odds i det vi mätt, och det är modulens normala driftfall.

⚠️ **Ekot ser ut som ett svar i funktionellt läge.** Ramen börjar själv på `0xC1`,
och halv-duplex ekar allt vi sänder. En naiv sökning efter `0xC1` i bursten hittar
vårt eget eko och rapporterar uppkoppling på tom buss (`C1! c1 29 f1 81`).
`fast_init_tolerant` hoppar därför över ekot innan den söker — och `1A 8A`-
kvittensen fångar resten.

**Stabiliteten ser löst ut:** tre hållperioder (2026-08-19 13:29, 13:40, 13:44)
gav 95/95, 95/95 respektive 71/71 lyckade läsningar på 1 Hz — noll tappade. Det
är starkt men fortfarande n=3, och alla under samma eftermiddag.

`0xC1` = funktionellt adressläge (bit 7-6 = 11) i stället för fysiskt `0x81`.
Jakten fick svar **enbart** i funktionellt läge med `0xF1`, samma kombination som
muki01-referensen använder. `Slabs._init_variants` växlar därför numera: udda
försök fysiskt/F7, jämna funktionellt/F1. Testa systematiskt med
`tools/slabs_probe.py`, som kör hela matrisen med tysta perioder emellan och
loggar rå TX/RX.

## ReadEcuIdentification — `1A xx`
| Req | Svar | Innehåll |
|---|---|---|
| `1A 8A` | 28 byte `00 37 44 60 44 03 10 ff 31 90 10 86 40 ff 06 29 …` | hårdvaru-/config-ID |
| `1A 8B` | ASCII | **mjukvarumoduler:** `KRTE49B0 HDTE16A0 EBTE87A0 CDTE91A0 KWTP11A0` |
| `1A 8D` | ASCII | **VIN:** `SALLXXXXXXXXXXXXX` ✅ (bekräftar avkodningen) |

## Felkoder
- **`21 11`** → 16-byte block = **LOGGADE fel** (bit-per-fel). Före clear: bitar satta
  i byte 3 (`0x10`) + byte 10 (`0x10`) = **två fel = baslinjens `020` RF-givare +
  `027` shuttle valve**. Efter clear: allt `00`. ⇒ `21 11` ÄR loggat-fel-blocket.
- **`21 47`** → 16-byte block = **AKTUELLA fel** (var `00` = inga aktuella nu).
- **`14 FF FF`** → `54` = **ClearFaults** (säker write; nollställde `21 11`).
- Byte↔nummer-mappning: 2 bitar (byte3.bit4, byte10.bit4) = fel 020+027. Fler
  ankarpunkter fås med "framkalla känt fel"-tekniken.

## Live-data — ReadDataByLocalIdentifier `21 xx`
Grupperat efter reference tool-skärm (värden = exempel):
- **SLS inputs:** `21 53`=`d2 d2 0f 0f` · `21 54`=`91 9c 0f 0f` (höjder, ändrades live) ·
  `21 55`=`00 00 00 02` · `21 45`=`7f` · `21 46`=`78 76` · `21 49`=`00 00 01` ·
  `21 59`=`00 0f 0f 0f`
- **ABS inputs:** `21 43`=`7c 00 7c 00 7c 00 7c 00` (**4 hjulhastigheter**) ·
  `21 44`=`00 80 01 02 01 01 02 01 02 02 03 04 …` · `21 50`=`72 73 73 72`
  (**givarspänningar?**) · `21 57`=`06 0f 0f 0f` · `21 49`=`00 00 01`
- **ABS-SLS switch:** `21 42`=`82` · `21 48`=`94 61` · `21 56`=`01 0f 0f 0f` ·
  `21 58`=`32 0f 0f 0f`

## Ställdon / tester — StartRoutine `31 xx` → svar `71 xx 20`
**Detta är skriv-/styrprotokollet.** Alla svarar `71 <rid> 20`.
| Kommando | Funktion |
|---|---|
| `31 25 <p>` | **ABS-pumprelä** (`31 25 08 fa 5c`=på, `31 25 02 fa 56`) |
| `31 2F 28` | **SLS avluftningsventil** (exhaust valve) |
| `31 30 28` | **SLS kompressor** |
| `31 31 0a` | **SLS summer** |
| `31 33 28` | **höj vänster** |
| `31 34 28` | **höj höger** |
| `31 35 28` | **sänk vänster** |
| `31 36 28` | **sänk höger** |
| `31 22 <sub> <p…>` | **ABS bleed + hjultester** (12-byte param) |

**`31 22`-subkommandon** (byte efter `22` väljer krets, sedan `<flags> c1 f4 …`):
| sub | funktion (ur markörer) |
|---|---|
| `04` | ABS power bleed (`31 22 04 00 49 c4 …`) |
| `11` | front left / module bleed steg 1 (`31 22 11 0c c1 f4` = FL-test; `…11 00 c0 7d 00 bb` = bleed) |
| `10` | front right (`31 22 10 03 c1 f4`) |
| `13` | rear left (`31 22 13 c0 c1 f4`) |
| `12` | rear right (`31 22 12 30 c1 f4`) |
| `14` | module bleed steg 4 |
**Flagg-byten = 2-bitars-mask per hjul (avkodat 2026-08-07):** `03`=HF (bit 0–1),
`0c`=VF (bit 2–3), `30`=HB (bit 4–5), `c0`=VB (bit 6–7) — dvs 2 bitar (in-/ut-ventil)
per hjul i ordningen HF, VF, HB, VB. `sub` = `0x10 + hjulindex` (HF=0…VB=3). `c1 f4`
konstant (trolig varaktighet/timeout). Live-data är också hjulvis: `21 43`=4
hjulhastigheter, `21 50`=4 givarspänningar → passar en hjul-orienterad UI perfekt.

**OBS — lamptester saknas rent:** instrumentlamptesterna (TC/ABS/HDC/broms/SLS-lampor)
kördes bara i den FÖRSTA sessionen (baud-krock → skräp). Byten är obrukbara; funktionen
finns men måste **loggas om** (lista gärna reference tool-ordningen samtidigt).

## Att bygga i d2diag (allt underlag finns nu)
`Slabs(KWP2000(KLine(...)))`: establish() via fast init 0x29 → C1 57 8F; keepalive 3E;
`read_faults()` = `21 11`/`21 47` (bit-per-fel, karta i `slabs_fault_codes.md`);
`clear_faults()` = `14 FF FF`; live via `21 xx`; ställdon via `31 xx`. Återanvänd
Td5-lagrets toleranta läsning + samma sessionsmönster.

## Input-LID:er (sniffat 2026-08-08, full per-input-svep)
reference tool pollar en fast LID-uppsättning per skärm; operatören stegade igenom
posterna. Alla input-LID:er nu identifierade (offset/skala per post återstår att
isolera med riktade captures):

| Skärm | LID:er | Poster |
|---|---|---|
| SLS-inputs | `21 53`, `21 54`, `21 55` | L/R sensor value (**`21 54` b0/b1 avkodad**), sensor supply, value (V), exhaust valve (V), compressor relay (V) |
| ABS-inputs | `21 43`, `21 44`, `21 49`, `21 50`, `21 57` | hjulhastighet (`21 43`), ABS-sensor V (`21 50`), in-/utloppsventiler, pump relay/monitor, batteri, ECU-supply, ground ref, HDC brake, engine speed/torque/throttle (via CAN) |
| Switchar | `21 42`, `21 48`, `21 56`, `21 58` | neutral, low range, diff lock, reverse, HDC, shuttle, **any-door (`21 56` byte0 bit0 — BELAGT: 00 stängd/01 öppen)**, plip |
| Settings | `21 45`, `21 46`, `21 49`, `21 59` | **Stabila råbytes belagda (RDL 016):** `45`=`7f`, `46`=`78 76`, `49`=`00 00 01`, `59`=`00 0f 0f 0f`. ⚠️ **LID→setting OLÖST** — två ordningsbaserade märkningar motsäger varandra (kortordning ostabil). Lös med DIFFERENTIAL: växla EN setting → se vilken råbyte ändras. |

## Byte-varians ur session.log (`analyze_capture.py --variance`)
Vilka bytes som **rörde sig** under captet = redan-differential-kandidater. Smalnar
av vad som ska korreleras mot reference tool-värden:

| LID | Byte-struktur (belagt ur varians) |
|---|---|
| `21 54` | **byte0 = vänster höjd, byte1 = höger höjd** (båda varierar = live). Bekräftat. |
| `21 50` | 4 byte, **en ABS-sensor-spänning per hjul** (~`0x72`); byte1/2 varierade (två hjul). |
| `21 43` | konstant `7c 00 ×4` stillastående = hjulhastighets-**baslinje** (≠0). |
| `21 53` | byte0 ~`d1/d2` varierar (supply-kandidat); byte1 konst, byte2/3 = `0f 0f`. |
| `21 55` | byte3 varierar (litet värde 00/02/03); resten `00`. |
| `21 57` | byte0 varierar (`05/06/08`); resten `0f 0f 0f`. |
| `21 44` | **rikt block** — offsets 2,3,4,6,8–13 varierar (ventiler/pump/batteri/supply). Kräver labels. |
| `21 49` | konstant `00 00 01`. |

**TD5-switchar (session.log):** `21 1E` byte1 = switch-bitfält (togglade `CA`→`EA`
= bit `0x20`; byte0 konst); `21 36` konstant `00 0D` (fixa switchar). Vi vet alltså
*vilken byte* men inte *vilken switch* — kräver annoterad toggle.

## Fält-identitet ur reference tool-skärmläsning 2026-08 (struktur belagd, skala kandidat)
Värden avlästa på skärmen, korrelerade mot gammal råbyte (ej samma ögonblick →
skala = kandidat). **Struktur (vilken LID = vilken skärmsektion) är belagd** via
visningsordning + värdeintervall:

| LID | Fält | Kandidat |
|---|---|---|
| `21 43` | **4× hjulhastighet** (2 byte/hjul) | stillastående `7c 00` = 1,7 km/h (baslinje) |
| `21 50` | **4× ABS-sensor-spänning** (1 byte/hjul) | FR byte0 `0x72`=114 → 2,17 V (≈×0,019); FL blank i reference tool |
| `21 44` | **stort analogblock (14 byte):** 8 ventilspänningar + pump relay/monitor + batteri + ECU-supply | ventiler `0x01–03`→ ×0,01 V (0,01–0,03); **byte12/13 = batteri/ECU-supply** (~`0xb3/b1`→ ×1/16 ≈ 11,3–11,5 V; VARIERAR = matchar) |
| `21 53` | **L/R sensor-supply** (byte0/1) | `0xd1`=209 → ~5 V (≈×0,024); byte2/3 `0f 0f` |
| `21 54` | **L/R höjd** (byte0=vä, byte1=hö) | **belagt** (149/162) |
| `21 55` | compressor relay | byte3 `0x02` → 0,13 V (kandidat) |
| `21 49`/`21 57` | CAN-härlett: engine speed (brus 195–235 motor av), torque, throttle | throttle 0–86 vid gaspådrag |

⚠️ **Exakt byte↔ventil-ordning och skalor kräver EN färsk sniff-capture** (rå +
reference tool-värde i samma ögonblick) av ABS-/SLS-inputs-skärmarna. Utan det är detta
taket. Batteri/ECU-supply (21 44 byte12/13) är starkast — de varierar och matchar.

**Nästa steg för full avkodning:** riktade differential-captures — ändra EN sak
(öppna en switch, lyft en hörna, mät en spänning) och jämför råbytesen före/efter.
Kör `analyze_capture.py --variance <logg>` för kandidaterna direkt.
