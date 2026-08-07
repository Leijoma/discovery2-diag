# Discovery 2 SLABS (Wabco) — felkodslista

Numrerade feltyper för SLABS-ECU:n (self-levelling + ABS). Källa:
[rswsolutions.com — Discovery II ABS Codes](https://rswsolutions.com/category/discovery-ii-abs-codes/)
(paginerad, hämtad 2026-08-07). reference tool-guiden anger "up to 47 different faults";
rsw listar fler numrerade poster (012–114) — troligen inkl. länk-/motorrelaterade.

> ⚠️ **Detta är DISPLAY-numren (verktygets), inte nödvändigtvis råa K-line-index.**
> Precis som för Td5 måste vi korsvalidera **rå fault-byte/bit ↔ nummer ↔ text**
> genom att **sniffa reference toolen** när den läser SLABS-felkoder (fånga både råbytes
> och den visade koden samtidigt). Först då kan `d2diag`-SLABS-avkodaren byggas.

## Systematisk struktur (viktig ledtråd)
Koderna är regelbundna → råindex lär mappa systematiskt. Per **8 ventiler**
(4 hjul × in/ut) och per **feltyp** finns en kod:
open circuit → short to gnd → short to supply → **drive** short to supply.
Samma för **4 hjulhastighetsgivare** (electric fail / output low / bad output),
**pump-relä**, **bromsljus-relä** och **pump** (monitor/sticking/running).

## Full lista

| Kod | Beskrivning |
|---|---|
| 012 | Pump Fail — Monitor Line |
| 013 | Pump Fail — Pump Not Running When On |
| 014 | Pump Fail — Pump Sticking |
| 015 | Pump Fail — Pump Running When Not On |
| 016 | Shuttle Valve Switch Long Term Failure |
| 017 | ECU Internal Valve Relay Bad |
| 020 | No Batt Supply Voltage |
| 021 | Engine PWM Signal Bad |
| 022 | ECU Gnd or Reference Gnd Bad |
| 023 | Gear Info Not Valid |
| 030 | Front Right In Valve — Open Circuit |
| 031 | Front Right Out Valve — Open Circuit |
| 032 | Front Left In Valve — Open Circuit |
| 033 | Front Left Out Valve — Open Circuit |
| 034 | Rear Right In Valve — Open Circuit |
| 035 | Rear Right Out Valve — Open Circuit |
| 036 | Rear Left In Valve — Open Circuit |
| 037 | Rear Left Out Valve — Open Circuit |
| 040 | Pump Relay — Open Circuit |
| 041 | Brake Light Relay — Open Circuit |
| 044 | Front Right Sensor — Output Low |
| 045 | Rear Left Sensor — Output Low |
| 046 | Front Left Sensor — Output Low |
| 047 | Rear Right Sensor — Output Low |
| 050 | Front Right In Valve — Short To Gnd |
| 051 | Front Right Out Valve — Short To Gnd |
| 052 | Front Left In Valve — Short To Gnd |
| 053 | Front Left Out Valve — Short To Gnd |
| 054 | Rear Right In Valve — Short To Gnd |
| 055 | Rear Right Out Valve — Short To Gnd |
| 056 | Rear Left In Valve — Short To Gnd |
| 057 | Rear Left Out Valve — Short To Gnd |
| 060 | Pump Relay — Short To Gnd |
| 061 | Brake Light Relay — Short To Gnd |
| 064 | Front Right Sensor — Electric Fail |
| 065 | Rear Left Sensor — Electric Fail |
| 066 | Front Left Sensor — Electric Fail |
| 067 | Rear Right Sensor — Electric Fail |
| 070 | Front Right In Valve — Short to Supply |
| 071 | Front Right Out Valve — Short to Supply |
| 072 | Front Left In Valve — Short to Supply |
| 073 | Front Left Out Valve — Short to Supply |
| 074 | Rear Right In Valve — Short to Supply |
| 075 | Rear Right Out Valve — Short to Supply |
| 076 | Rear Left In Valve — Short to Supply |
| 077 | Rear Left Out Valve — Short to Supply |
| 080 | Pump Relay — Short To Supply |
| 081 | Brake Light Relay — Short to Supply |
| ~082–089 | Sensor — Bad Output (Front Right / Rear Left / Front Left / Rear Right) *(exakta nummer ej fångade — verifiera)* |
| 090 | Front Right In Valve — Drive Short to Supply |
| 091 | Front Right Out Valve — Drive Short to Supply |
| 092 | Front Left In Valve — Drive Short to Supply |
| 093 | Front Left Out Valve — Drive Short to Supply |
| 094 | Rear Right In Valve — Drive Short to Supply |
| 095 | Rear Right Out Valve — Drive Short to Supply |
| 096 | Rear Left In Valve — Drive Short to Supply |
| 097 | Rear Left Out Valve — Drive Short to Supply |
| 100 | Pump Relay — Drive Short to Supply |
| 101 | Brake Light Relay — Drive Short to Supply |
| 110 | Sticking Throttle Detected |
| 111 | Shuttle Valve Sticking |
| 112 | Internal ECU comms error |
| 113 | Shuttle Valve Switch Dynamic Failure |
| 114 | Shuttle Valve Switch Electrical Failure |

## Tre-amigos-koppling
"Tre amigos" (ABS + TC + HDC-lampor) tänds vid många av dessa — särskilt
**hjulhastighetsgivar-fel** (044–047 low, 064–067 electric fail, ~082–089 bad
output) och **shuttle valve** (016, 111, 113, 114). Vid sniffen: läs SLABS-felkoder
och notera vilka som är **Current** vs **Intermittent** + räknare → korsa mot denna lista.
