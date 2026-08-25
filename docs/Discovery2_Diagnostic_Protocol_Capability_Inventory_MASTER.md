# Land Rover Discovery 2 Diagnostic Protocol Capability Inventory

**TD5 · SLABS · BCU/DCU · ACE · Auto Gearbox · Airbag**

Consolidated inventory of module capabilities, observed K-line behavior, established hex commands, and unresolved areas. It serves two purposes: a technical handoff and working reference for continued implementation in d2diag, and a **shareable progress report for the Discovery 2 / Td5 community** — to show how far this open reverse-engineering effort has come and to exchange findings and experience. Vehicle-identifying values and security credentials are deliberately excluded (see §11).

# 1. How to read this document

This document separates established protocol behavior from strong candidates and open questions. Observed function ordering and field wording are preserved where they may matter for byte/bit mapping.

| **Status**       | **Meaning**                                                                                            |
|------------------|--------------------------------------------------------------------------------------------------------|
| ESTABLISHED      | Observed directly in raw traffic or verified against the vehicle in multiple observations.             |
| STRONG CANDIDATE | The structure is supported by multiple observations, but exact semantics/bit mapping are not proven.   |
| OPEN             | The function is known to exist or appears in traffic, but there is insufficient evidence to decode it. |
| NOT ESTABLISHED  | No separate function or traffic has been verified; it should not be implemented as fact.               |

Important methodology rule: logger comments often land in the middle of an already-running stream. An annotation must therefore be associated with the traffic regime/screen and searched backward in time, rather than automatically assigned to the nearest frame.

# 2. Common protocol patterns

## 2.1 TD5/SLABS-style KWP2000 framing

After initialization, TD5 and SLABS use unaddressed length-prefixed frames:

> \<len\> \<SID\> \<data...\> \<checksum\>

Checksum = the sum of all preceding bytes modulo 256. A positive response is normally SID + 0x40. Examples: 21 → 61, 31 → 71, 3E → 7E.

| **Service** | **Meaning**                         |
|-------------|-------------------------------------|
| 21 / 61     | ReadDataByLocalIdentifier           |
| 30 / 70     | InputOutputControlByLocalIdentifier |
| 31 / 71     | StartRoutine / actuator test        |
| 33 / 73     | RoutineResults                      |
| 3E / 7E     | TesterPresent                       |
| 1A / 5A     | ReadECUIdentification               |
| 14 / 54     | Clear diagnostic information        |
| 27 / 67     | SecurityAccess                      |

## 2.2 SLABS initialization

| **Item**                   | **Hex / behavior**                                  | **Status / notes**                                                                                                                                        |
|----------------------------|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fast-init physical address | 0x29                                                | ESTABLISHED                                                                                                                                               |
| StartCommunication         | 81 29 F7 81 22                                      | ESTABLISHED                                                                                                                                               |
| Response                   | 03 C1 57 8F AA                                      | ESTABLISHED; C1 = positive response to 0x81, 57/8F keywords.                                                                                              |
| Keepalive                  | 01 3E 3F → 01 7E 7F                                 | ESTABLISHED, approx. 1 Hz.                                                                                                                                |
| StopCommunication          | 01 82 83 → 01 C2 C3                                 | ESTABLISHED in our own implementation.                                                                                                                    |
| Fast-init TiniH            | Empirically adjusted until connection became stable | ESTABLISHED as the root cause of the previous sporadic initialization attempts. The exact working timing value should be retained in code/protocol notes. |

Practical conclusion: SLABS proved significantly more sensitive to effective TiniH than TD5. Once TiniH was adjusted, initialization became stable; the application layer had been correct throughout.

# 3. TD5 Engine ECU (Lucas)

**ESTABLISHED** The base protocol, live data, most outputs, and security status are largely solved. Settings and switch bitfields are still only partially mapped.

## 3.1 Fault codes

| **Function**      | **Hex**                  | **Status**                    | **Explanation**                                                                                                                                             |
|-------------------|--------------------------|-------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Read fault block  | 21 3B                    | ESTABLISHED                   | 35-byte bit block. The working decoder uses bit index offset×8+bit; approximately 210 relevant bit positions have been mapped against the fault dictionary. |
| Clear faults      | 14/54 family             | ESTABLISHED at service level  | The exact TD5 clear sequence exists in code/logs; keep it separate from SLABS 14 FF FF.                                                                     |
| Current vs logged | Separate status memories | ESTABLISHED at function level | Active/current and logged states are distinct. Exact raw status encoding per fault is not fully documented here.                                            |

## 3.2 Inputs

Switch Inputs. The interface exposes the following 12 items in order. Traffic on this screen is dominated by LIDs 1E and 36. Byte 1 of LID 1E has been observed switching CA\<-\>EA (bit 0x20), but the exact switch\<-\>bit mapping is not yet complete.

| **\#** | UI label          | Known raw structure | **Status / notes**          |
|--------|-------------------|---------------------|-----------------------------|
| 1      | Brake Switch 1    | 21 1E / 21 36       | OPEN individual bit mapping |
| 2      | Brake Switch 2    | 21 1E / 21 36       | OPEN individual bit mapping |
| 3      | Clutch Switch     | 21 1E / 21 36       | OPEN individual bit mapping |
| 4      | Transfer Ratio    | 21 1E / 21 36       | OPEN individual bit mapping |
| 5      | Gear Box          | 21 1E / 21 36       | OPEN individual bit mapping |
| 6      | Cruise Control    | 21 1E / 21 36       | OPEN individual bit mapping |
| 7      | Cruise Resume     | 21 1E / 21 36       | OPEN individual bit mapping |
| 8      | Set Accelerate    | 21 1E / 21 36       | OPEN individual bit mapping |
| 9      | AC Clutch Request | 21 1E / 21 36       | OPEN individual bit mapping |
| 10     | AC Clutch Drive   | 21 1E / 21 36       | OPEN individual bit mapping |
| 11     | AC Fan Request    | 21 1E / 21 36       | OPEN individual bit mapping |
| 12     | AC Fan Drive      | 21 1E / 21 36       | OPEN individual bit mapping |

Fuelling / live engine data. Several LIDs and scalings are established here:

| Observed value                    | **LID**            | **Encoding**                                          | **Status**            |
|-----------------------------------|--------------------|-------------------------------------------------------|-----------------------|
| Engine Speed                      | 21 09              | u16 BE, rpm                                           | ESTABLISHED           |
| Idle Speed Error                  | 21 21              | s16 BE, rpm                                           | ESTABLISHED           |
| Road Speed                        | 21 0D              | 1 byte, km/h candidate; 0 when stationary             | HIGH                  |
| Battery                           | 21 10              | u16/1000 V                                            | ESTABLISHED           |
| Accel. Way 1–3 + Supply           | 21 1B              | 4 × u16 BE /1000 V                                    | ESTABLISHED           |
| Coolant/Fuel/Air inlet + ext temp | 21 1A              | temperature block, u16/10 − 273.2 for verified fields | ESTABLISHED/PARTIAL   |
| MAP / manifold                    | 21 1C              | MAP at offset 0 (u16 BE ×0.0001 bar) established; 1C@4 is NOT air mass (reads 0 while running) | ESTABLISHED (MAP)     |
| MAF (air mass)                    | 21 1D              | u16 BE @4; proven as the field (r=+0.95 vs rpm×MAP over a full WOT pull); kg/h scale is a CANDIDATE pending a reference | ESTABLISHED (field)   |
| Injection quantity                | 21 1D              | u16 BE @6, ×0.01 mg/stroke                            | ESTABLISHED           |
| Ambient + manifold pressure       | 21 23              | 2 × u16; displayed in kPa                             | ESTABLISHED structure |
| Cylinder 1–5 balances             | 21 40              | 5 × s16 BE                                            | ESTABLISHED           |
| EGR modulator                     | 21 1D              | u8 @15, ×100/255 % duty                               | STRONG CANDIDATE      |
| Wastegate modulator               | 21 1D              | u8 @17, ×100/255 % duty                               | STRONG CANDIDATE      |
| EGR/wastegate NOT at 21 37/38     | 21 37 / 21 38      | do not respond on this vehicle — dismissed            | NOT ESTABLISHED       |

## 3.3 Outputs

| Output                   | **Hex command**       | **Status / notes**              |
|--------------------------|-----------------------|---------------------------------|
| A/C CLUTCH               | 30 A3 FF              | ESTABLISHED                     |
| A/C FAN                  | 30 A4 FF              | ESTABLISHED                     |
| MIL LAMP                 | 30 A2 FF              | ESTABLISHED                     |
| FUEL PUMP                | 30 A1 FF              | ESTABLISHED                     |
| GLOW PLUGS               | 30 B3 FF              | ESTABLISHED                     |
| PULSE REV COUNTER        | 30 B7 FF              | ESTABLISHED                     |
| WASTEGATE MODUL.         | 30 BE FF + PWM        | ESTABLISHED; parameter/PWM used |
| TEMP GAUGE               | 30 BA FF              | ESTABLISHED                     |
| EGR THROTTLE / modulator | 30 BD FF + PWM        | ESTABLISHED                     |
| INJECTOR 1–5             | 31 C2 01 ... 31 C2 05 | ESTABLISHED                     |

## 3.4 Utilities

| **Function**        | **Hex**                  | **Status / notes**                                                                             |
|---------------------|--------------------------|------------------------------------------------------------------------------------------------|
| LEARN SECURITY CODE | 31 C0-related routine    | Function exists; the full write sequence should be kept separate from status reading.          |
| GET SECURITY STATUS | 31 C0 ; 33 C0 → 73 C0 03 | ESTABLISHED. Status 03 matched “ECU not immobilized” and is a strong candidate for this state. |

## 3.5 Settings

Settings contain several data types and should not be treated as one homogeneous block. In the observations, settings are retrieved through several one-shot LIDs, including 21 3D, 21 20, 21 0E, 21 32, and 21 24. Exact LID→field mapping is not yet complete.

| **Group**      | Fields                                                                                                                                                                                                                                                                                                    | **Known protocol**                      | **Status**                                                                          |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------|-------------------------------------------------------------------------------------|
| Injector codes | Injector 1–5 (5 characters each), INJ. TYPE                                                                                                                                                                                                                                                               | Bulk/read-write not fully isolated      | UI + baseline established; write format open                                  |
| Read-only ID   | Config Tune ID; Fuel Tune ID; ECU Part Number; Homologation; GET VIN                                                                                                                                                                                                                                      | Part of settings/ID reads               | Function/field established; exact requests per field partially open                             |
| Feature config | Temperature Gauge; Tachometer; SLABS; Road Speed; Radiator Fan; MIL Lamp; Fuel Used; Fuel Temperature; EGR Modulator; EGR Inlet; Cruise Lamp; Cruise Control; Clutch Switch; CAN Bus; Auxiliary Fan; Auto Gearbox; Air Conditioning; Active Engine mount; Ambient Sensor; Wastegate Modulator; ECU Status | 21 3D / 20 / 0E / 32 / 24 occur in bulk | UI order established; individual byte/bit mapping requires differential observation |

Baseline structure (vehicle-identifying values redacted): Config Tune ID, Fuel Tune ID, ECU Part Number, and Homologation are read as read-only ID fields here. Feature-config values are booleans (ENABLED/DISABLED) plus an ECU Status enum — e.g. Temperature Gauge, Tachometer, SLABS, Road Speed, Radiator Fan, MIL, Fuel Used, Fuel Temperature, EGR Modulator, EGR Inlet, Cruise Control, ECU Status. The specific per-field values are not published here.

# 4. SLABS (Wabco ABS/SLS)

ESTABLISHED Initialization and the base session are solved. Fault read/clear, several live LIDs, and many actuator/bleed commands have been directly observed. Individual settings mapping and some lamp/analog fields remain open.

## 4.1 Fault codes

| **Function**   | **Hex**                                       | **Status / explanation**                                                                          |
|----------------|-----------------------------------------------|---------------------------------------------------------------------------------------------------|
| Logged faults  | 21 11 → 16-byte bit block                     | ESTABLISHED. Before clear, two bits were set; after clear the block became zero.                  |
| Current faults | 21 47 → 16-byte bit block                     | ESTABLISHED. At baseline the block was 00 = no current faults.                                    |
| Clear faults   | 14 FF FF → 54                                 | ESTABLISHED and tested on the vehicle.                                                            |
| Known baseline | example: one wheel-sensor fault + one valve fault (specific codes redacted) | Correlated with the displayed fault state; the full 47-fault bit map requires more anchor points. |

## 4.2 Inputs

| Screen           | **LIDs**                          | **What we know**                                                                                                                      | **Status** |
|------------------|-----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|------------|
| SLS Inputs       | 21 53, 21 54, 21 55               | 21 54 byte0=left height, byte1=right height. 53/55 contain supply/value/exhaust/compressor-related data, but scaling is not complete. | PARTIAL    |
| ABS Inputs       | 21 43, 21 44, 21 49, 21 50, 21 57 | 21 43 = 4 wheel speeds; 21 50 = 4 wheel sensor-voltage channels; 44/49/57 contain valve/pump/supply/HDC/engine-related fields.        | PARTIAL    |
| ABS-SLS Switches | 21 42, 21 48, 21 56, 21 58        | Any Door Open = 21 56 byte0 bit0 is confirmed. Other signals: neutral, low range, diff lock, reverse, HDC, shuttle, plip.             | PARTIAL    |

## 4.3 Outputs

| **Function**             | **Hex**                           | **Status / notes**                                                                                                                         |
|--------------------------|-----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| ABS pump relay           | 31 25 \<p\>                       | ESTABLISHED. 31 25 08 FA observed as ON; 31 25 02 FA as the other/reset state.                                                             |
| SLS exhaust valve        | 31 2F 28                          | ESTABLISHED                                                                                                                                |
| SLS compressor           | 31 30 28                          | ESTABLISHED                                                                                                                                |
| SLS buzzer               | 31 31 0A                          | ESTABLISHED                                                                                                                                |
| Raise left               | 31 33 28                          | ESTABLISHED                                                                                                                                |
| Raise right              | 31 34 28                          | ESTABLISHED                                                                                                                                |
| Lower left               | 31 35 28                          | ESTABLISHED                                                                                                                                |
| Lower right              | 31 36 28                          | ESTABLISHED                                                                                                                                |
| Wheel inlet/outlet tests | 31 22 \<sub\> \<params...\>       | ESTABLISHED structure; sub 10=FR, 11=FL, 12=RR, 13=RL.                                                                                     |
| Instrument lamp tests    | TC/ABS/HDC/brake/SLS/offroad etc. | NOT DECODED. In the final test session, only TesterPresent was transmitted while the UI showed inactive; no new 31 routines were observed. |

## 4.4 Utilities

| **Utility**                       | **Hex / structure**   | **Status**                                                                     |
|-----------------------------------|-----------------------|--------------------------------------------------------------------------------|
| ABS Power Bleed                   | 31 22 04 00 49 C4 ... | ESTABLISHED                                                                    |
| ABS/Module Bleed – wheel circuits | 31 22 10/11/12/13 ... | ESTABLISHED wheel selection; parameters include a 2-bit mask per wheel.        |
| Additional module bleed step      | 31 22 14 ...          | ESTABLISHED as a separate sub-ID; exact step semantics not fully documented |

## 4.5 Settings

| **LID** | **Observed baseline** | **Status / interpretation**                                                                |
|---------|-----------------------|--------------------------------------------------------------------------------------------|
| 21 45   | 7F                    | ESTABLISHED raw value; individual setting unknown                                          |
| 21 46   | 78 76                 | ESTABLISHED raw value; individual setting unknown                                          |
| 21 49   | 00 00 01              | ESTABLISHED raw value; also used on the ABS input screen, so context must be kept separate |
| 21 59   | 00 0F 0F 0F           | ESTABLISHED raw value; individual setting unknown                                          |

Important limitation: two order-based attempts to associate these LIDs with individual settings produced contradictory results. No individual SLABS setting should therefore be marked as solved without a controlled A/B/A differential test.

# 5. BCU / DCU (Valeo body system)

STRONG CANDIDATE The BCU function set is well documented. EKA read/write is solved. BCU output traffic shows four WriteLocalIdentifier banks and SecurityAccess, but individual output and settings bit mapping is not yet solved.

## 5.1 Fault codes

No conventional BCU Faults screen or DTC capability is established in the available material. The BCU should therefore not be given a speculative fault list until an actual function or raw traffic demonstrates it.

## 5.2 Inputs

| Group              | **Items**                                                                                                                                                                                                                                                                                                                                               | **Protocol status**                                                                                             |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| LIGHTS             | Side lights; Main beam; Dipped; Front fog light; Rear fog light; Left indicator; Right indicator; Hazard; Daytime run light                                                                                                                                                                                                                             | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| DOORS / BODY       | Passenger door switch; Driver door switch; Bonnet; Key lock; Key unlock; CDL Lock; CDL unlock; Inertia; Ignition key inserted; Transfer box neutral; Park/neutral                                                                                                                                                                                       | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| TRANSMISSION       | Reverse idle; Transfer neutral switch; Autobox W switch; Autobox X switch; Autobox Y switch; Autobox Z switch; Park neutral switch                                                                                                                                                                                                                      | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| WINDOWS            | Front LEFT down; Front LEFT up; Front RIGHT down; Front RIGHT up                                                                                                                                                                                                                                                                                        | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| WASH WIPE          | Front intermit; Front wash; Front wiper parked; Front wiper speed; Rear wiper; Rear wash                                                                                                                                                                                                                                                                | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| HEATED / ENGINE    | Heated screen switch; Ignition 2; Engine speed signal                                                                                                                                                                                                                                                                                                   | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| INSTRUMENTS        | LH DI; RH DI; LH Tailor DI; RH Tailor DI; Seat belt; Diff lock; Transfer neutral; Autobox manual; Autobox sport; Offroad level; ABS; Traction control; SRS; HDC select; Glow plug; Brake; Oil pressure; Alternator; Check engine; Fuel filter; Transmission temp.; Check ACE; Check HDC; Check SLS; Instr. milage (km); BCU milage (km); IP trip switch | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |
| POWER DISTRIBUTION | BCU ignition pos. 1; BCU ignition pos. 2; BCU ignition pos. 3; IP ignition pos. 2; IDM ignition pos. 2; IDM battery (V); BCU switch power; BCU relay power                                                                                                                                                                                              | Raw LID/bit mapping has not yet been systematically associated with every item. Preserve grouping and order. |

## 5.3 Outputs

The BCU exposes two ordered output blocks: BODY (17 items) and SECURITY/LOCKING (14 items). Observed traffic provides structural evidence for four 32-bit WriteLocalIdentifier banks:

3B 22 xx xx xx xx  
3B 23 xx xx xx xx  
3B C1 xx xx xx xx  
3B C2 xx xx xx xx

All observed payloads were 00 00 00 00. Therefore, no individual output may yet be assigned to a particular bit. The strongest hypothesis is that these are diagnostic output/control banks and that zero writes represent reset/inactive/housekeeping operations.

| **Block**          | Items                                                                                                                                                                                                                                                                                                                                 | **Status**                                     |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------|
| BODY               | Front fog lights; Rear fog lights; Daytime running lights; LH indicator enable; LH indicator enable (UI duplicate); Front left window up/down; Front right window up/down; Rear windows enable; Sunroof enable; Front wiper enable; Tail wiper enable; Head lamp power wash; Heated screen; Heat. rear screen lamp; Check engine lamp | UI complete. Individual bank/bit mapping OPEN. |
| SECURITY / LOCKING | Horn; BBUS ALL; BBUS ST; Fuel flap; Alarm LED; Ignition interlock; Crank Enable; Volumetric power; Robust immo.; Transponder Power; Lock; Unlock; Superlock; Single point entry                                                                                                                                                       | UI complete. Individual bank/bit mapping OPEN. |

## 5.4 Utilities

| **Utility**                  | **Known traffic**                       | **Status / explanation**                                                                                                         |
|------------------------------|-----------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| EKA CODE READ                | 21 CC                                   | ESTABLISHED                                                                                                                      |
| EKA CODE SET                 | 3B CC d1 d2 d3 d4                       | ESTABLISHED. Write format is 3B CC \<d1\> \<d2\> \<d3\> \<d4\>. No vehicle-specific EKA value or credential example is included. |
| Key Code 1–4 + Susp / UPDATE | Function set documented                           | Protocol not mapped; six-hex-digit credential fields exist.                                                                    |
| KEY DETECT / SYNC            | Key 1–4 + SUSP, SYNC; global KEY DETECT | Function set documented; protocol open.                                                                                                    |
| Suspension plip BAR CODE     | BAR CODE; SET CODE 1; UPDATE            | Function set documented; protocol open.                                                                                                    |

## 5.5 SecurityAccess / auth

BCU write/output sessions use classic KWP SecurityAccess (SID 0x27). We have at least one clean seed/key observation and additional key observations:

| **Step**             | **Hex**       | **Status / notes**                                                                          |
|----------------------|---------------|---------------------------------------------------------------------------------------------|
| Request seed         | 27 01           | ESTABLISHED                                                       |
| Seed response        | 67 01 \<seed\>  | ESTABLISHED structure; concrete seed bytes redacted              |
| Key attempt          | 27 02 \<key\>   | ESTABLISHED structure; a mismatched key returns 7F 27 83         |

What is missing is the vendor-specific seed→key algorithm itself. **Concrete seed/key values are deliberately excluded from this public document** — they are immobiliser SecurityAccess material and are dual-use. Brute force should be avoided because SecurityAccess may use an attempt counter or lockout. A safer approach is to collect/recover several complete seed/key pairs (kept private) and then derive the algorithm.

## 5.6 Settings

| Group                | **Items**                                                                                                                                                                                                                                                  | **Known protocol status**                                                |
|----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| LIGHTS WINDOWS-SEATS | Front fog lamp; Daytime run lights; Courtest head lamps; Headlamp power wash; Electric window front; Rear windows sunroof; Heated front screen; Electric front seats; Programmed wash wip; Seat belt warning; Seat belt warning soun; Autographics         | Settings LIDs occur, but individual LID/bit mapping is not resolved.     |
| TRANSM-LOCK-WARN     | Transmission; Shift Interlock; HDC; Superlock; Single point entry; Speed lock option; Mislock option; Bathrobe lock option; Odometer error warn; Key warning; Low battery warning; Bulb failure                                                            | UI exactly documented.                                                   |
| INSTRUMENT PACK      | Transmission; Engine; ACE; SLS; Gulf; Police; HDC; TRC                                                                                                                                                                                                     | Likely packed config block; individual mapping open.                     |
| ALARM-OTHER          | Alarm; Alarm option; Alarm disarm; Alarm sounder; Alarm tamper; Engine immobil.; Passive immobil.; Inertia switch; Hazard option; Volumetric sensor; Market; EKA option; Cruise control; Air conditioning; Fuel burning heater; Passive coil; Transit mode | Mixture of Boolean + enum fields; good differential target.              |
| INFO                 | Serial No; Date; Hardware No; Software No; Alarm Type; VIN                                                                                                                                                                                                 | Read-only identification rather than live input. Fields and example values verified. |

Observed BCU settings IDs include C7, CA, CB, D3, EB, C6, CE, D4, D5, D6, and D7. They should be treated as identified LID candidates, not as fully named fields.

# 6. ACE (Lucas)

PARTIAL The functions for inputs, outputs, and utilities are documented. The raw protocol uses a different bulk format from TD5/SLABS, and ACE is disabled on the test vehicle, making the fault baseline difficult to interpret.

## 6.1 Fault codes

| **Function**       | **Raw traffic**                                             | **Status / explanation**                                                                   |
|--------------------|-------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| Read faults        | 67 \| 67 11 \<18-byte fault block\> | ESTABLISHED fault-block structure from one session (a 67-framed block after the 67 11 header). Specific decoded fault codes redacted. |
| Clear faults       | 8C \| 8C 00                                                 | ESTABLISHED                                                                                |
| Keepalive / status | 04 \| 04 00 ; 07 \| 07 00                                   | ESTABLISHED as recurring exchanges                                                         |

Important revised interpretation: duplicated bytes such as 67 67, 04 04, 07 07, 8C 8C, 15 15, and 65 65 are best explained as a request byte followed by a response whose first byte echoes the command, because direction is not encoded in the available one-wire traffic logs. E0 E0 and F0 F0, however, occur inside the payload and are genuine duplicated payload bytes. ACE is disabled on the test vehicle, so observed valve/pressure faults may be secondary effects and do not reliably identify the original fault.

## 6.2 Inputs

| **\#** | UI label                     | **Raw structure / status**                                                         |
|--------|------------------------------|------------------------------------------------------------------------------------|
| 1      | Engine Speed (rpm)           | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 2      | Road Speed (Km/h)            | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 3      | Battery Voltage (V)          | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 4      | DCV1 Current (AMP)           | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 5      | DCV2 Current (AMP)           | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 6      | PCV Current (AMP)            | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 7      | Pressure Sensor (bar)        | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 8      | Residual Pressure (bar)      | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 9      | System Pressure (bar)        | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 10     | Upper Lateral Acccelerometer | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 11     | Lower Lateral Acccelerometer | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 12     | Ignition Switch              | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 13     | Reverse Switch               | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 14     | Main Relay                   | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |
| 15     | Warning Lamp                 | A common 65 bulk block streams at ~1 Hz; individual offset/scaling not yet mapped. |

The core input exchange is 41 bytes. The log also contained 44-byte gap frames in which a separate 07 \| 07 00 keepalive had been appended directly after the 41-byte block. This proves that the gap logger sometimes merges logical exchanges and that keepalive traffic must be stripped before offset mapping.

## 6.3 Outputs

| Output                | **Status**                                                                    |
|-----------------------|-------------------------------------------------------------------------------|
| Main relay(Force ON)  | Function/field established; exact raw command not reliably mapped in the current material |
| Main relay(Force OFF) | Function/field established; exact raw command not reliably mapped in the current material |
| Warning Lamp          | Function/field established; exact raw command not reliably mapped in the current material |
| Dir. Control Valve 1  | Function/field established; exact raw command not reliably mapped in the current material |
| Dir. Control Valve 2  | Function/field established; exact raw command not reliably mapped in the current material |

## 6.4 Utilities

| **Utility**            | **Hex**      | **Status**                               |
|------------------------|--------------|------------------------------------------|
| Calib. Accelerometer 1 | 15 \| 15 FF  | ESTABLISHED                              |
| Calib. Accelerometer 2 | 16 \| 16 FF  | ESTABLISHED                              |
| Set Calibrated         | 10 \| 10 00  | ESTABLISHED                              |
| OIL BLEEDING STEP 1    | START / STOP | Function/field established; raw command not isolated |
| OIL BLEEDING STEP 2    | START / STOP | Function/field established; raw command not isolated |
| OIL BLEEDING STEP 3    | START / STOP | Function/field established; raw command not isolated |

## 6.5 Settings

No separate ACE Settings screen is established in the available material. The calibration functions are under Utility and should not be moved to Settings merely because they change persistent state.

# 7. Auto Gearbox — Bosch GS8.87.0

PARTIAL The ECU responds deterministically using its own 0x72-framed protocol, even when the diagnostic interface reports that the function could not be performed. Function requests are well identified, but data contents and frame semantics are not yet fully decoded.

## 7.1 Fault codes

| **Function** | **Request**    | **Response**               | **Status / notes**                                                                                                  |
|--------------|----------------|----------------------------|---------------------------------------------------------------------------------------------------------------------|
| Read faults  | 72 05 04 00 73 | 72 09 60 01 00 00 00 00 1B | CONFIRMED/reproduced in a separate final session. Do not yet interpret 01 00 00 00 00 as a fault count or DTC list. |
| Clear faults | 72 04 05 73    | 72 04 60 99 FF             | CONFIRMED/reproduced. 60/99 FF appears to be a generic acknowledgement/session structure; semantics open.           |

## 7.2 Inputs

The GENERAL screen has 26 items in exact observed UI order:

| **\#** | UI label                | **Known request**                     |
|--------|-------------------------|---------------------------------------|
| 1      | Throttle position (%)   | 72 05 0B 03 7F (entire GENERAL block) |
| 2      | Engine torque (%)       | 72 05 0B 03 7F (entire GENERAL block) |
| 3      | Torque requested (%)    | 72 05 0B 03 7F (entire GENERAL block) |
| 4      | Reduced torque (%)      | 72 05 0B 03 7F (entire GENERAL block) |
| 5      | Friction torque (%)     | 72 05 0B 03 7F (entire GENERAL block) |
| 6      | Torque reference (Nm)   | 72 05 0B 03 7F (entire GENERAL block) |
| 7      | Gear switch W           | 72 05 0B 03 7F (entire GENERAL block) |
| 8      | Gear switch X           | 72 05 0B 03 7F (entire GENERAL block) |
| 9      | Gear switch Y           | 72 05 0B 03 7F (entire GENERAL block) |
| 10     | Gear switch Z           | 72 05 0B 03 7F (entire GENERAL block) |
| 11     | Program switch          | 72 05 0B 03 7F (entire GENERAL block) |
| 12     | High/Low range switch   | 72 05 0B 03 7F (entire GENERAL block) |
| 13     | Kick down               | 72 05 0B 03 7F (entire GENERAL block) |
| 14     | Shift type              | 72 05 0B 03 7F (entire GENERAL block) |
| 15     | Engine speed (RPM)      | 72 05 0B 03 7F (entire GENERAL block) |
| 16     | Turbine speed (RPM)     | 72 05 0B 03 7F (entire GENERAL block) |
| 17     | Output speed (RPM)      | 72 05 0B 03 7F (entire GENERAL block) |
| 18     | Battery (V)             | 72 05 0B 03 7F (entire GENERAL block) |
| 19     | Solenoid valve 1        | 72 05 0B 03 7F (entire GENERAL block) |
| 20     | Solenoid valve 2        | 72 05 0B 03 7F (entire GENERAL block) |
| 21     | Solenoid valve 3        | 72 05 0B 03 7F (entire GENERAL block) |
| 22     | Modulator pressure      | 72 05 0B 03 7F (entire GENERAL block) |
| 23     | Engine temperature (°C) | 72 05 0B 03 7F (entire GENERAL block) |
| 24     | Adaptive program 1      | 72 05 0B 03 7F (entire GENERAL block) |
| 25     | Adaptive program 2      | 72 05 0B 03 7F (entire GENERAL block) |
| 26     | Adaptive program 3      | 72 05 0B 03 7F (entire GENERAL block) |

The separate pressure-input request is 72 05 0B 00 7C. The exact pressure UI fields and byte offsets are not yet sufficiently verified.

## 7.3 Outputs

No separate Auto Gearbox Outputs screen is established in the available material. Leave the category unimplemented until an actual function or traffic demonstrates otherwise.

## 7.4 Utilities

| **Utility**                            | **Hex**              | **Status**                                                                                    |
|----------------------------------------|----------------------|-----------------------------------------------------------------------------------------------|
| Reset Adaptive / reset adaptive values | 72 06 83 FF 07 08 FF | ESTABLISHED request; response/semantics should continue to be logged as a separate 72 routine |

## 7.5 Settings

| **Function / UI**     | **Hex / data**                                                            | **Status**                                       |
|-----------------------|---------------------------------------------------------------------------|--------------------------------------------------|
| Read Settings         | 72 05 93 00 E4                                                            | ESTABLISHED request                              |
| Settings response     | 72 18 60 69 65 15 95 ...                                                  | Data block observed; field decoding open         |
| Identification fields | Manufacturer; Softw. level; Coding index; CAN Softw. level; Softw version | Function/field established                                   |
| Part/VIN fields       | LR Part number; Manuf. part number; Vehicle VIN; WRITE VIN                | Function/field established; VIN-write request not yet mapped |

# 8. Airbag — TRW SPS Type 2A

PARTIAL The fault record format is decoded. Settings/identification are documented, but no separate live Inputs, Outputs, or Utilities screen is established.

## 8.1 Fault codes

| **Function**     | **Hex**                                            | **Status / explanation**                                        |
|------------------|----------------------------------------------------|-----------------------------------------------------------------|
| Read fault class | 21 02 → 61 02 + \[status\]\[fault-number\] records | ESTABLISHED. Fault number matches the displayed value directly. |
| Observed record  | 90 04                                              | Fault 004: Airbag warning lamp open circuit intermittent.       |
| Observed record  | 90 16                                              | Fault 022: Left pretensioner open circuit intermittent.         |
| Other read class | 21 01                                              | Observed empty in the observation; exact class meaning open.    |
| Clear faults     | 14 → 54                                            | ESTABLISHED; addressed KWP frame in the raw log.                |

Status byte 0x90 is a strong candidate for “open circuit intermittent”, but the general meaning of the status bits requires more faults/observations.

## 8.2 Inputs

No separate live Inputs screen is established. Do not implement speculative inputs.

## 8.3 Outputs

No separate Outputs screen is established.

## 8.4 Utilities

No separate Utilities are established.

## 8.5 Settings

| **\#** | Fields                  | **Status / notes**                                                                    |
|--------|-------------------------|---------------------------------------------------------------------------------------|
| 1      | Manufacturer            | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 2      | Model                   | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 3      | Software version        | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 4      | Hardware version        | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 5      | Serial number           | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 6      | Date of build           | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 7      | Part reference          | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 8      | Part number             | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 9      | VIN                     | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 10     | Driver's airbag         | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 11     | Passenger's airbag      | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 12     | Right hand Pretensioner | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 13     | Left hand Pretensioner  | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 14     | Driver's side airbag    | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 15     | Passenger's side airbag | Function/field established; identification/configuration. Only VIN is documented as programmable. |
| 16     | Rolamites               | Function/field established; identification/configuration. Only VIN is documented as programmable. |

# 9. Consolidated capability matrix

| **Module**   | **Fault codes**                                   | **Inputs**                              | **Outputs**                            | **Utilities**                                      | **Settings**                                                   |
|--------------|---------------------------------------------------|-----------------------------------------|----------------------------------------|----------------------------------------------------|----------------------------------------------------------------|
| TD5          | Very good                                         | Very good                               | Almost fully solved                    | Known security routines                            | Extensive UI; bulk mapping partly open                         |
| SLABS        | Read/current/logged/clear solved                  | Groups + several mappings               | Many actuators; lamp tests missing     | ABS bleed known                                    | LID group known; individual mapping open                       |
| BCU/DCU      | No conventional screen established                | Very extensive function set                       | Entire function list known; bank/bit mapping open | EKA solved; keys/plip UI known                     | Very extensive; LID/bit mapping open                           |
| ACE          | Read/clear structure established, fault bits open | 15 UI items; bulk offsets open          | 5 UI items; raw mapping open           | 3 calibration commands established + 3 bleed steps | No separate screen established                                 |
| Auto Gearbox | Read/clear confirmed                              | GENERAL complete; pressure group exists | No separate screen established         | Reset adaptive established                         | Read request + UI identification established; data decode open |
| Airbag       | Record format + clear established                 | No separate screen established          | No separate screen established         | No separate screen established                     | 16 identification/config fields established                    |

# 10. Highest-priority open questions

- BCU SecurityAccess: derive the seed→key algorithm from several complete seed/key pairs without brute force.

- BCU outputs: observation a non-zero write to bank 22/23/C1/C2, then map one output bit at a time.

- BCU settings: map C7/CA/CB/D3/EB/C6/CE/D4/D5/D6/D7 to exact configuration fields using single-change differential observations.

- TD5 settings: map 21 3D/20/0E/32/24 to the 21 feature fields and the injector/ID blocks.

- TD5 switch inputs: isolate the bits in 21 1E/21 36 by toggling one switch at a time.

- SLABS settings: map 45/46/49/59 to individual settings. Lamp-test routines are still missing.

- SLABS analog inputs: complete scaling/offset mapping in 53/55/44/50/57.

- ACE: leave parked until the system is actually repaired; the fault pattern may be an effect of ACE being disabled.

- Auto Gearbox: decode 0x72 framing and payload before naming field values.

- Airbag: collect more fault/status combinations to resolve status byte 0x90 and the relationship between 21 01 and 21 02.

# 11. Document status and safety note

This master intentionally excludes vehicle-identifying values, security credentials, and provenance details while retaining the protocol structure required for implementation. Uncertain associations are explicitly marked as OPEN or STRONG CANDIDATE.

This document is a protocol inventory, not a guarantee of safe service procedures. Write/actuator functions can affect brakes, suspension, immobilization, and configuration. In an implementation, read-only functions should be kept separate from writes, and all writes should require explicit user action.
