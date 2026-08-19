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

## Problemet i en mening

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
| **Kabel/buss/vår kod** | TD5 kopplar upp på första försöket sekunder före och efter varje misslyckat SLABS-försök, på samma kabel | **Uteslutet.** |

**Mönster som återstår:** träffarna klustrar i tiden. Ett fönster 13:29–13:47 gav
4 träffar; därefter 54 raka tysta försök över 86 minuter under alla betingelser.
Vi har ingen variabel som förklarar när fönstren öppnar.

## Den kända luckan: init-pulsens elektriska tajming

Sniffarna är **RX-only** och ser bara UART-data. Den elektriska väckningspulsen
före `81 29 F7 81 22` finns därför inte i något capture — vi vet inte hur det
kommersiella verktyget timar den.

ISO 14230-2 fast init: buss tyst ≥ 300 ms (W5) → K-line **låg 25 ms ± 1** (TiniL)
→ **hög 25 ms ± 1** → StartCommunication direkt.

**Vår implementation:**

- Låg-pulsen är hårdvarutimad: vi sänker baudraten till ~360 och skickar en `0x00`
  (startbit + 8 nollor = 9 låga bitar ≈ 25 ms). Bestäms av UART:ens bitklocka,
  inte av OS:et.
- **Den höga perioden är `time.sleep(0.025)`** — OS-timad.
- Därefter en `flush()` och en USB-write innan byten når tråden. **FTDI:s latency
  timer är 16 ms som default**, och USB-schemaläggningen lägger på ytterligare.
- **Vi har inget explicit W5** (300 ms buss-idle) före pulsen.

Faktisk tid från pulsens slut till första byten kan därför vara 25–45 ms i stället
för 25. Vi har precis lagt in mätning av detta (`low_ms`, `high_ms`,
`to_frame_ms`) men har ännu inga siffror från bilen.

Jämförelse: en ESP32 som bit-bangar pulsen (300 ms idle, 25 ms låg, 25 ms hög,
sedan UART) har mikrosekundsnoggrannhet och ingen USB-buffert emellan.

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
   finns det något vi kan göra på USB-sidan först (latency timer, W5, annan
   pulsmetod)?

## Vad vi INTE söker hjälp med

Applikationslagret ovanför `C1` — det är löst, verifierat och stabilt. Frågan
gäller enbart att komma in.
