# BCU — nyckelkodning + tändnings-egenhet (mål & research)

Två saker att utforska när vi **loggar BCU:n** (Valeo, slow init, permanent matad —
svarar även med tändning av). Ingen av dessa är gjord än; detta är målbild + vad
som krävs + riskbild.

## ⚠️ BCU = brick-zonen — läs först
BCU:n innehåller **immobilisern**. reference tool-guiden är tydlig:
> *"A LOCKED BCU CANNOT BE UNLOCKED BY DIAGNOSTIC METHODS."*

Fel skrivning mot immobilisern kan **låsa/immobilisera bilen**. All nyckel-/
immobiliser-skrivning görs bara:
- med **EKA-koden** känd (Emergency Key Access — matas via förardörrens lås),
- med minst en **fungerande nyckel** kvar,
- stillastående, stabil ström, aldrig avbruten mitt i en skrivning.

## 1. Tändnings-egenheten (att verifiera vid BCU-loggning)
Användaren minns att någon modul (troligen **BCU**) krävde: **slå av tändningen →
initiera dialogen → slå på tändningen**. Guiden säger att BCU/larm generellt
kommunicerar med **tändning av**. Den exakta sekvensen (kanske för en specifik
funktion som EKA/nyckelprogrammering) **verifieras när vi sniffar BCU** — logga
init:en i olika tändningslägen och notera vad som krävs.

## 2. Nyckelkodning — mål
Programmera in en **ny nyckel** (transponder) via BCU:n. reference tool stödjer det
(guiden nämner **key programming** + EKA). Det vore mycket värdefullt (extranyckel,
begagnad nyckel, förlorad nyckel).

**Vad som krävs innan vi kan implementera:**
1. **Sniffa BCU-init** (slow init-adress + keybytes; jfr 0x40 i vårt slow-svep).
2. **Sniffa läs-funktioner först** (ofarligt) → bekräfta protokoll/header-format.
3. **Sniffa en riktig nyckelprogrammerings-session** med reference tool (⚠️ skriver mot
   immobilisern — gör bara med EKA + reservnyckel). Fånga: säkerhetsåtkomst
   (seed/key?), EKA-inmatning, själva programmerings-rutinen, kvitton.
4. **Förstå säkerhetsalgoritmen** (seed→key) om sådan krävs — jfr Td5:ans keygen.

**Path:** läs-sniff (säkert) → förstå format → nyckel-sniff (riskabelt, med EKA) →
implementera `d2diag.bcu`-lager med **hårda säkerhetsspärrar** (kräv explicit
bekräftelse + EKA + "reservnyckel finns"-flagga innan skrivning).

## Status
- BCU: **ej sniffad** än. Vet bara: slow init, permanent matad, svarar tändning av,
  läses av reference tool 1 (denna bils reference tool klarade BCU-läsning).
- Nästa: logga BCU med ESP32-tappen (läs-funktioner) → sedan detta.
Se [[valeo_bcu_capabilities.md]] och `references/d2_diagnostic_overview.md`.
