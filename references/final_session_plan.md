# Kort reference tool-session — fånga exakt detta (prioriterat)

Vi har redan **råbytesen** för det mesta (ur `session.log`) — det vi saknar är
reference tools **klartext-värden** att korrelera mot. Därför är de mest värdefulla
uppgifterna **"läs på skärmen"** och behöver **inte** ens en fungerande sniff.

## 0. Snabbkoll av sniffern (30 s)
Fångst → **Ny insamling** → ser du ×N **klättra**? Ja = sniff funkar (fånga rå
samtidigt). Nej = strunta i sniffen, kör bara **A** nedan (räcker för det mesta).

## A. HÖGST VÄRDE — läs av alla värden på skärmen (ingen sniff behövs)
Skriv av **alla** värden i **visad ordning** (statiska värden ≈ desamma som i vår
gamla capture → vi korrelerar mot råbytesen offline):

1. **SLABS → ABS Inputs** — hjulhastighet FR/FL/RR/RL · ABS-sensor V FR/FL/RR/RL ·
   in-/utloppsventiler · pump monitor/relay · battery · ECU supply · ground ref ·
   HDC brake · engine speed/torque/throttle. → mot `21 43/44/49/50/57`.
2. **SLABS → SLS Inputs** — L/R sensor value (höjd) · L/R sensor supply · L/R value (V) ·
   exhaust valve (V) · compressor relay (V). → mot `21 53/54/55`.
3. **TD5 → Settings → Feature/config** — ENABLED/DISABLED för alla 21 flaggor i
   ordning + ECU Status. → löser `21 3D`-blocket.

## B. OM sniffern är stabil — differential (ändra EN sak i taget, annotera)
4. **SLABS settings:** växla **Transport mode** (säkert, reversibelt) → skriv
   "växlade transport mode". → löser vilken av `45/46/49/59` = transport + kodningen.
5. **TD5 read switch:** tryck **broms** → **koppling** → **cruise ON**, en i taget,
   annotera var. → mappar bitfälten `21 1E`/`21 36`.

## C. Om tid — autobox
6. **Auto Gearbox → Read Faults** med **motor igång** + väljare i **P**. Lyckas den →
   vi får tolkningsbara `72 … 60 …`-svar (ramning redan löst: `72 <len> <data> <XOR-cs>`).

## Efteråt
Klistra in anteckningarna (eller ge loggfilen) → jag korrelerar mot råbytesen och
mappar fälten offline. **A räcker för att lösa SLABS-analogen och TD5-featureblocket.**
