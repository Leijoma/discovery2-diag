# Full datatäckning + MAF-fyndet (Td5)

Skriven 2026-08-21. Princip, metod och konkreta fynd från MAF-jakten på RDL016.

## Princip: fånga ALL mottagen data, inte bara mappade fält

Varje TD5-poll ger ett helt datablock per LID. De bytes vi inte döpt är precis där
omappade signaler gömmer sig. Två delar:

1. **Polla allt reference tool pollar** — även LID:er vi inte kan mappa än, så råloggen
   fångar dem (se `web/sources.py`, `_TD5_COVERAGE_EXTRA` + `_SLABS_COVERAGE`).
2. **Analysera allt** — `tools/raw_analyze.py` läser en rålogg och visar per LID
   vilka byte-positioner som rör sig, varje u16-offset + korrelation mot RPM, och
   vad som är mappat vs omappat.

## MAF hittad: `21 1D` byte 5 (u8, kg/hr) — BELAGT

**Metoden som knäckte det:** rådata från en körning med varvtalet i rörelse
(`tools/lid_sweep.py --seconds 75`, tomgång→2000→2500), sedan **byte-nivå-binning
mot rpm** — inte bara u16. MAF visade sig vara **ETT byte**, inte u16.

Biltest 2026-08-21 (RDL016, motorn igång):

| rpm | 1D byte5 |
|---|---|
| tomgång (~780) | **69** |
| ~2000 | **184** |

Följer belastningen (2.7×). Matchar publicerade Td5 reference tool-intervall: tomgång
55–65, 2000 rpm 185–200, hög last 3000 rpm 550–600, overboost-cut ~618–650.

**Givaren är FRISK.** Motsäger det tidigare "död MAF"-spåret. Bekräftat vid
kontakten (CO149, 3-polig): 12 V på pin 3, pin1–2 = 17 kΩ (facit ~16,8 kΩ), och
live-signalen följer rpm. `maf_raw` (1C@4 = 0 vid körning) var ALDRIG MAF utan ett
statusfält.

⚠️ **Attribution:** skalan (råvärde = kg/hr direkt) är matchad mot **forum-intervall**,
inte en reference tool-avläsning på RDL016 själv. Identifieringen (fältet ÄR MAF) är stark;
finjustera skalan om en reference tool-avläsning blir tillgänglig.

## ext_temp = spöke (1A@8 konstant 0x1088 = 150 °C)

Extern temp-givare finns INTE monterad på Td5-ECU:n. `21 1A@8` är en konstant som
avkodas till exakt 150,0 °C. Verklig utetemp (~17 °C) kommer från bilens egen
kluster-givare via BCU, inte motor-ECU:n. Fältet har fått gränser `[-40,50]` så
150 flaggas **suspect** (överstruken) i UI:t i stället för att se ut som en temp.

## Täcknings-implementation

- **TD5** (ej sessionskänslig): läser de bekräftat svarande omappade LID:erna
  **1E, 1F, 20** varje cykel (utöver de mappade), så de samplas jämte rpm för
  framtida korrelation. `1D` pollas nu automatiskt eftersom `maf` finns i storen
  (`LIDS` härleds ur storen).
- **SLABS** (måste pollas LÄTT — block-läsning dödar sessionen, se
  `slabs_protocol.md`): hela reference tool-input-blocket (`11,3B,42–59`) roteras **EN
  LID per cykel**; 0x54-höjderna läses varje cykel. Trafiken förblir ~1 Hz.

## Öppet / nästa steg

- **Bredare LID-discovery:** vi vet att 1D–20 svarar; en sweep över fler TD5-LID:er
  (0x0E–0x40) kan avslöja fler svarande block att lägga i täckningen.
- **1D:s övriga bytes rör sig med rpm:** byte1 (27→65), byte11 (50→127) — troligen
  bränslemängd/insprutning, omappade. Fångas nu i råloggen varje poll.
- Verktyg: `tools/raw_analyze.py <rålogg>` (offline, alla LID:er + rpm-korrelation),
  `tools/lid_sweep.py` (live, läser även opollade LID:er + rankar mot rpm).
