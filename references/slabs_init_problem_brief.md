# SLABS-anslutning: problembeskrivning för extern granskning

_Skriven 2026-08-19. Fristående — förutsätter ingen kännedom om vår kodbas._

## Uppställning

- Bil: Land Rover Discovery 2 Td5 (2000), reg RDL 016. Diagnostik över **K-line**
  (ISO 14230 / KWP2000) på OBD-stift 7. Ingen CAN.
- Interface: generisk **USB-KKL 409.1** (FTDI FT232), macOS, `/dev/cu.usbserial-*`,
  10400 baud 8N1. pyserial + egen protokollstack i Python.
- Moduler på samma buss: TD5 motor-ECU (Lucas, fysisk adress `0x13`), **SLABS**
  (Wabco ABS + självnivellerande luftfjädring, `0x29`), airbag (`0x5B`), m.fl.
- Referensmaterial: passiva sniffar (ESP32, RX-only på stift 7) av ett kommersiellt
  verktyg som kör hela funktionsuppsättningen mot bilen.

## ✅ LÖST 2026-08-19 kl 17:26 — orsaken var vår egen init-puls

Dokumentet skrevs medan problemet var öppet. Det står kvar som dokumentation av
felsökningen, men **orsaken är hittad och åtgärdad**:

Vår TiniH (höga perioden mellan låg-pulsen och StartCommunication) var **~32 ms
i stället för 25 ± 1**, av två skäl: UART-stoppbiten efter puls-byten (~2,8 ms)
räknades inte, och `time.sleep(25 ms)` överskjuter till 25,3–32,0 ms (median 29,1)
på macOS. Med stoppbiten avdragen och en spinnande väntan i stället för `sleep`:

| | Träffkvot per initförsök |
|---|---|
| Före (TiniH ~32 ms) | 3/32 = **9 %** |
| Efter (TiniH 25,00 ± 0,01 ms) | 6/11 = **55 %** |

Fishers exakta test: **p = 0,007**. Fem körningar i rad gav träff, varje gång på
första eller andra försöket — och tre av dem på `81 29 F7 81 22`, alltså exakt
den ram vi kört hela tiden. **Adressläget var aldrig problemet.**

Slutsatsen är den hypotes som föreslogs vid granskning: en Wabco-modul har ett
smalare toleransfönster för fast-init-timing än TD5:ans Lucas-ECU, som accepterade
vår felaktiga puls utan protest.

## Problemet som det såg ut (historik)

**TD5 kopplar upp på första försöket i stort sett varje gång. SLABS svarar på
ungefär 1 av 10 initförsök — men när den väl svarar är sessionen helt stabil.**

## Vad som är belagt

**Applikationslagret är löst och verifierat mot bilen.**

| Sak | Värde |
|---|---|
| StartCommunication (fysisk) | `81 29 F7 81 22` |
| Svar | `03 C1 57 8F AA` (len, C1 = 0x81+0x40, KW1, KW2, checksumma) |
| Sessionsramar | `<len> <SID> <data…> <cs>`, oadresserade |
| Checksumma | summa av föregående bytes & 0xFF |
| Positivt svar | SID + 0x40 |
| Första begäran efter C1 | `02 1A 8A A6` → `5A 8A …` (verktyget gör alltid detta) |
| Keepalive | `01 3E 3F` → `01 7E 7F`, ~1 Hz. **Bar 3E — `3E 01` river sessionen** |
| Felkoder | `21 11` loggade / `21 47` aktuella, 16-byte bitblock |
| Live-data | `21 54` = höjd vänster/höger i byte 0/1 |
| StopCommunication | `01 82 83` → `01 C2 C3` |

**Stabilitet efter uppkoppling:** tre hållperioder à 2 minuter på 1 Hz gav 95/95,
95/95 och 71/71 lyckade läsningar — noll tappade. En session har hållits 5 min 31 s
och avslutades bara för att vi bytte modul. Modulen är alltså inte trasig.

**Kända krav:** tändning på; comms dör över 8–20 km/h (bekräftat — försök under
körning är alltid tysta).

## Vad vi har mätt och FÖRKASTAT som förklaring

Alla siffror är från kontrollerade körningar 2026-08-19 med slumpad ordning.

| Hypotes | Mätning | Slutsats |
|---|---|---|
| **Adressläge** (fysisk `81` vs funktionell `C1`, testar F7 vs F1) | med slumpad ordning: funktionell/F1 1/8, funktionell/F7 1/9, fysisk/F7 1/7, fysisk/F1 0/8 | **Ingen effekt.** En tidigare "effekt" (6/24 mot 1/21) visade sig vara sammanblandad med försöksnumret — fast ordning i matrisen. |
| **P4, inter-byte-tid vid sändning** (0 ms vs 5 ms enligt ISO 14230-2 och muki01-referensen) | 0 ms: 1/17 · 5 ms: 2/15 | Inget utslag, men n är litet. Hypotesen lever svagt. |
| **Tyst period före init** (5 s vs 10 s vs 30 s) | såg signifikant ut (p=0,017) men var helt sammanblandad med tidpunkt | **Förkastad som bevis.** Träffar har senare kommit efter 5 s tystnad. |
| **Motorn igång vs av** | igång 3/10, av 1/15 — Fishers exakta p = 0,27 | Tendens, ej signifikant. Senare körningar med motorn igång gav 0/20. |
| **Batterispänning** | träffar 12,11–13,91 V, missar 11,83–13,80 V | Ingen tröskel, intervallen överlappar helt. |
| **Kvarlämnad session från annan modul** | `7F 81 10` (generalReject) förekom, kom från TD5 i öppen session | **Åtgärdat** — vi skickar `82` StopCommunication vid teardown och före init. Rejecten är borta sedan dess. |
| **Dörr öppen/stängd** | 0 träffar på 2 körningar med öppen dörr | För litet för slutsats. |
| **Kabel/buss/vår kod** | TD5 kopplar upp på första försöket sekunder före och efter varje misslyckat SLABS-försök, på samma kabel | Grundläggande K-line-hårdvara och sessionskod **fungerar**, verifierat mot TD5. Men **modulberoende tolerans för fast-init-timing är fortfarande öppen** — TD5 (Lucas) kan mycket väl ha ett bredare fönster än SLABS (Wabco). Det är den hypotes som passar observationen bäst. |

**Mönster som återstår:** träffarna klustrar i tiden. Ett fönster 13:29–13:47 gav
4 träffar; därefter 54 raka tysta försök över 86 minuter under alla betingelser.
Vi har ingen variabel som förklarar när fönstren öppnar.

## Den kända luckan: init-pulsens elektriska tajming

Sniffarna är **RX-only** och ser bara UART-data. Den elektriska väckningspulsen
före `81 29 F7 81 22` finns därför inte i något capture — vi vet inte hur det
kommersiella verktyget timar den.

ISO 14230-2 fast init: buss tyst ≥ 300 ms (W5) → K-line **låg 25 ms ± 1** (TiniL)
→ **hög 25 ms ± 1** → StartCommunication direkt.

**Vår implementation — och två fel som hittades 2026-08-19 vid extern granskning:**

- Låg-pulsen är hårdvarutimad: vi sänker baudraten till ~360 och skickar en `0x00`
  (startbit + 8 nollor = 9 låga bitar ≈ 25 ms). Bestäms av UART:ens bitklocka.
- 🐛 **Stoppbiten glömdes bort.** UART-ramen avslutas med en stoppbit som är HÖG —
  vid 360 baud ≈ 2,8 ms — och `flush()` väntar tills den sänts. TiniH hade alltså
  redan börjat innan vår väntan startade.
- 🐛 **`time.sleep(0.025)` överskjuter grovt.** Uppmätt på maskinen i fråga:
  `sleep(25 ms)` tar i verkligheten **25,3–32,0 ms, median 29,1**.

  Summa: verklig TiniH var ≈ **32 ms** där ISO anger **25 ± 1**.

  **Åtgärdat:** stoppbitens längd dras nu av, och väntan görs med en spinnande
  klocka i stället för `sleep` → uppmätt **25,00 ± 0,01 ms** i vår kod.
- **W5 saknades helt** (ingen garanterad buss-idle före pulsen). Nu implementerat
  som `init_idle`, avstängt som default, och avsett att köras på 0,3–1,0 s.

⚠️ **Kvarstår omätt:** vi kan bara mäta vår egen mjukvarusida. Tiden från att
`write()` returnerar tills byten fysiskt lämnar FT232:n — USB-schemaläggning och
drivrutin — syns inte från Python. De verkliga elektriska flankerna är fortfarande
okända.

**Idé för att mäta dem:** vi har redan en ESP32 med RX-only-tapp på K-line. Den
kan tidsstämpla flankerna (fallande → stigande → startbit) och därmed mäta vad vår
USB-KKL faktiskt producerar — utan att behöva bygga om den till sändare.

Jämförelse: samma ESP32 kan även bit-banga pulsen själv (300 ms idle, 25 ms låg,
25 ms hög, sedan UART) med mikrosekundsnoggrannhet och ingen USB-buffert emellan.
Den sketchen finns redan och sänder mot TD5; att rikta om den mot `0x29` är en
konstantändring.

## Frågor vi vill ha hjälp med

1. **Är USB-KKL:ns tajming en trolig förklaring** till att en Wabco-modul avvisar
   init medan en Lucas-ECU på samma buss accepterar den? Är TiniH-fönstret känt
   för att vara snävt hos Wabco?
2. **W5** — hur strikt är kravet på 300 ms buss-idle före fast init i praktiken,
   och kan en modul hamna i ett tillstånd där den kräver betydligt längre?
3. Finns det **dokumenterat SLABS/Wabco-specifikt initbeteende** (t.ex. att modulen
   bara lyssnar i vissa fönster, kräver tändningscykel, eller går i viloläge när
   fordonet står parkerat)?
4. **Tidsklustringen** — 4 träffar på 18 minuter, sedan 0 på 86 minuter under
   identiska förutsättningar. Vilken mekanism i en ABS/SLS-ECU skulle ge det?
5. Är det värt att gå till **ESP32 i master-läge** för deterministisk puls, eller
   finns det något mer att hämta på USB-sidan först?

_Not: en tidigare version av det här dokumentet påstod att FTDI:s latency timer
(16 ms) lägger till fördröjning på sändsidan. Det är fel — den styr hur snabbt
MOTTAGNA data töms från chipets buffert till hosten. Påpekat och struket._

## Vad vi INTE söker hjälp med

Applikationslagret ovanför `C1` — det är löst, verifierat och stabilt. Frågan
gäller enbart att komma in.
