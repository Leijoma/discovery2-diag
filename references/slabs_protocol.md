# Wabco SLABS — komplett K-line-protokoll (sniffat från reference tool 1)

Fångat 2026-08-07 via passiv ESP32-tapp (RX-only, GPIO16) på pin 7, medan en lånad
**reference tool 1** körde hela funktionsuppsättningen. Rå logg + markörer:
`logs/session.log` (avkodas med `tools/decode_session.py`). Detta är **belagt ur
verklig trafik**, inte gissat.

## Grundläggande
- **Adress `0x29`, FAST init:** `81 29 F7 81 22` → svar `C1 57 8F` (KWP2000, KW2=8F).
- **Session:** oadresserade, längd-prefixade ramar `<len> <SID> <data…> <cs>`
  (checksumma = byte-summa & 0xFF), samma stil som Td5-sessionen.
- **Keepalive:** `01 3E` → `7E` (TesterPresent), ~1 s.
- Kräver **tändning PÅ** (tändningsmatad modul). Comms dör >8–20 km/h.

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
