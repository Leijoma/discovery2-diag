# Permanent ESP32 K-line install — RDL 016 (Disco 2 Td5, MY2000)

Verifierat mot bilens elscheman (`../Discovery 2/referens docs/`: Electrical Library
1999-05 + Circuit Diagrams 2000) 2026-08-26. Allt sitter i **förarsidans fotbrunn /
under instrumentbrädan** — diagnostikuttag, K-line-header och passagerarsäkringsdosa.

## K-line-tapp (läser hela bussen)

- **K-line = rosa ledning (LR-färgkod `K`), 0,5 mm²**, på **diagnostikuttagets pin 7**
  (uttag **V100**, kontakt **C0040**).
- **Alla moduler möts på header C0286 (K109)** — Td5-ECM, SLABS, BCU, EAT, ACE,
  Airbag hänger alla på samma K-wire dit; därifrån **en** rosa K-wire till uttaget.
- **Tapp-punkt:** den rosa pin-7-ledningen — bakom uttaget (pin 7, rosa) **eller** vid
  header C0286. Elektriskt samma delade buss → läser TD5, SLABS, BCU, airbag m.fl.
  med en tapp. Detta är "kabeln före OBD2-uttaget".

## Tändningsmatad 12 V

- Uttagets pin 16 (via säkring F20) är **PERMANENT** (klockminne) → **använd inte**
  (skulle dra på batteriet).
- **PRIMÄR (verifierad, läge I ELLER II): säkring F32 (accessory socket, 25 A)** i
  passagerardosan. Matas via **auxiliary circuits relay**: nyckel läge I/II →
  tändningslås → F26 → aux-relä stänger → fuse link 7 → **F32** → uttag (PG-ledning).
  Alltså spänning redan i **läge I** (accessory), *innan* tändning-run i läge II.
  ESP:n hinner boota i läge I och lyssnar från första ramen när bussen vaknar i II.
  Nyckel av → aux-reläet släpper → F32 dör → ingen batteridränering.
- Alternativ (läge II, tändning-run): **F29** (ACE/IDM/BCU, Y-ledning) — fungerar men
  senare. **F26** är också läge I/II men är aux-reläets *spolmatning* (välj F32).
  **Undvik:** F24 (ECM), F28 (SLABS), F23 (BCU/startrelä), F20 (permanent).
- **Metod:** piggyback-säkringstapp (add-a-fuse), originalkretsen orörd. Verifiera med
  testlampa: **död vid nyckel av, tänd redan i läge I**.

## Jord
OBD pin 4/5, eller jord-header **C0551 / C0017** (svart `B`-ledning), eller chassijord
i fotbrunnen.

## Designnoter (K-line-specifika)
- **ESP:n måste vara MASTER (TX+RX).** K-line är en **pollad** buss — modulerna
  broadcastar inte, de svarar bara på förfrågningar. Ingen sändning → ingen data. Så
  L9637D driver K-pinnen (rättelse: *inte* RX-only/passiv). ESP32:ns µs-bitbang gör
  init-pulsen (TiniH 25±1 ms) t.o.m. stabilare än USB-KKL.
- **Samexistens / mute (viktigt).** Bara EN master åt gången på bussen. När KKL-kabeln
  pluggas in måste ESP:n tystna — och **mute = avsluta sessionen rent (StopCommunication
  `82`) FÖRST, sen håll TxD idle.** Lämnar man en halvöppen session möts verktygets
  StartCommunication av `7F 81 10` (generalReject) — exakt buggen vi fixade i
  `slabs_protocol.md`. Rekommenderat: **listen-before-talk** (auto-backa när en annan
  masters init/ramar hörs) + en **hård mute** (GPIO/brytare el. firmware-kommando) vid
  KKL-inkoppling. Muted kan ESP:n passivt **sniffa** verktygets trafik (lär sig LID:er).
- **Belasta inte bussen** — K-line är känslig för kapacitiv last (hela timing-arbetet
  visar det); håll grenen kort, ingen extra kapacitans som rundar av flankerna.
- **Tapp bakom kontakten (master → pålitlig, låg resistans):** **lödtapp** på den rosa
  pin-7-tråden (skala fönster, löd gren, krymp). INTE Scotchlok. (OBD-hanplugg är
  onödig här — installen sitter bakom kontakten.)
- **Matningsskydd:** inline-säkring (~1 A) + fordonstålig buck (9–16 V in, TVS/load-dump
  + backspänningsskydd).

## Status
Analys sparad 2026-08-26; **install ej gjord än** (görs "när vi har tid i bilen").
