# reference tool master-menytranskription (Discovery 2) — referens

Källa: ägarens `reference tool_protocol_...docx` (AI-bearbetad avläsning av reference tools
online-emulator — nyare produkt, men samma menystruktur). **Exempelvärden är
capture-exempel, ej protokollkonstanter.** Driver modul-menykartorna (`*_MENU`)
och ger avkodnings-tips. Täcker: DCU/BCU (Instruments/Power/Settings/Outputs) +
roadmap för ACE/Autobox/Airbag.

```
reference tool communications protocol – Discovery 2
Verified master transcription – BCU/DCU screenshots reviewed 2026-08-08
DCU module – Read Inputs
Purpose. Working document for reverse-engineering reference tool communication with the Discovery 2 DCU. The menu labels below are transcribed exactly from the supplied reference tool screenshots. The “Screenshot value” column records only the state visible in those screenshots; it is not assumed to be the only possible value.
Capture workflow. For each input, change one physical condition at a time while logging K-line traffic. Record the reference tool request and ECU response, then compare captures to identify the byte/bit or encoded value that changes.
LIGHTS
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Side lights
OFF




2
Main beam
OFF




3
Dipped
OFF




4
Front fog light
OFF




5
Rear fog light
OFF




6
Left indicator
OFF




7
Right indicator
OFF




8
Hazard
OFF




9
Daytime run light
DISABLED





DOORS / BODY INPUTS
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Passenger door switch
CLOSE




2
Driver door switch
CLOSE




3
Bonnet
CLOSE




4
Key lock
IDLE




5
Key unlock
IDLE




6
CDL Lock
IDLE




7
CDL unlock
IDLE




8
Inertia
TRIGGER




9
Ignition key inserted
OUT




10
Transfer box neutral
OFF




11
Park/neutral
OFF





TRANSMISSION
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Reverse idle
OFF




2
Transfer neutral switch
OFF




3
Autobox W switch
OFF




4
Autobox X switch
OFF




5
Autobox Y switch
OFF




6
Autobox Z switch
OFF




7
Park neutral switch
OFF





WINDOWS
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Front LEFT down
OFF




2
Front LEFT up
OFF




3
Front RIGHT down
OFF




4
Front RIGHT up
OFF





WASH WIPE
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Front intermit
OFF




2
Front wash
OFF




3
Front wiper parked
OFF




4
Front wiper speed
6




5
Rear wiper
OFF




6
Rear wash
OFF





HEATED SCREEN / ENGINE STATE
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Heated screen switch
OFF




2
Ignition 2
ON




3
Engine speed signal
ACTIVE





Notes for protocol analysis
Keep “Transfer box neutral” and “Transfer neutral switch” as separate reference tool items until captures prove that they map to the same underlying signal.
Keep “Park/neutral” and “Park neutral switch” separate for the same reason.
The screenshot shows “Inertia = TRIGGER”. Verify whether this is a live state, a latched state, or reference tool wording for the input polarity before assigning protocol semantics.
“Front wiper speed” is numeric (6 in the screenshot), unlike the surrounding Boolean-style inputs. Treat it as a likely multi-bit or byte value until captures show otherwise.
Record full frames including initialization/session traffic where possible. Repeated requests are useful for identifying polling cadence and response length.
Capture session summary
Date / time

Vehicle / ECU variant

reference tool screen / function

K-line interface / sniffer

Baud / init method

Raw log filename

Comments


BCU module – Instruments
Purpose. Menu labels and displayed values transcribed from the supplied reference tool BCU → Instruments screenshots. As with the DCU section, the displayed values are capture examples only; they should not be treated as protocol constants.
BCU INSTRUMENTS – DISCRETE INPUTS / WARNING STATES
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
LH DI
OFF




2
RH DI
OFF




3
LH Tailor DI
OFF




4
RH Tailor DI
OFF




5
Seat belt
OFF




6
Diff lock
OFF




7
Transfer neutral
OFF




8
Autobox manual
OFF




9
Autobox sport
OFF




10
Offroad level
OFF




11
ABS
ON




12
Traction control
OFF




13
SRS
ON




14
HDC select
OFF




15
Glow plug
OFF




16
Brake
ON




17
Oil pressure
OFF




18
Alternator
OFF




19
Check engine
ON




20
Fuel filter
OFF




21
Transmission temp.
OFF




22
Check ACE
ON




23
Check HDC
ON




24
Check SLS
ON




BCU INSTRUMENTS – MILEAGE / TRIP INPUT
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
Instr. milage (km)
00468502




2
BCU milage (km)
00480000




3
IP trip switch
OFF




Notes for BCU protocol analysis
Preserve reference tool spelling exactly during reverse engineering. The screenshots show “LH Tailor DI”, “RH Tailor DI” and “milage”; these may be UI typos rather than protocol terminology.
The two mileage values are especially useful for determining whether reference tool requests instrument-pack mileage and BCU-stored mileage separately, and for identifying byte order and scaling.
Several displayed ON states are warning-lamp/status outputs rather than obvious switch inputs (for example ABS, SRS, Check engine, Check ACE, Check HDC and Check SLS). Treat the menu as an “instrument states” view rather than assuming every item is a direct BCU input.
For Boolean items, capture repeated frames while toggling only one physical condition at a time. For warning states that cannot be safely toggled, compare ignition-off, ignition-on/engine-off and engine-running captures.

BCU module – Power distribution
Purpose. Menu labels and displayed values transcribed from the supplied reference tool BCU → Power Distribution screenshots. Displayed values are capture examples only and should not be treated as protocol constants.
BCU POWER DISTRIBUTION – IGNITION / SUPPLY STATES
#
reference tool label
Screenshot value
Test / physical action
Request frame
Response frame
Candidate byte/bit / notes
1
BCU ignition pos. 1
ON




2
BCU ignition pos. 2
ON




3
BCU ignition pos. 3
OFF




4
IP ignition pos. 2
ON




5
IDM ignition pos. 2
ON




6
IDM battery (V)
12.7




7
BCU switch power
12.6




8
BCU relay power
12.6




Notes for BCU power-distribution protocol analysis
The three BCU ignition-position states are good candidates for a compact bit field. Capture frames at key removed, accessory/position 1, ignition on/position 2 and crank/position 3 if practical.
IP ignition pos. 2 and IDM ignition pos. 2 may be separate status reports from the instrument pack (IP) and Intelligent Driver Module (IDM), even though both follow the same ignition condition.
The three voltage values are especially useful for determining numeric encoding and scaling. Record several known battery voltages with a multimeter and compare the raw response bytes.
Because IDM battery, BCU switch power and BCU relay power are close but not identical, do not assume reference tool derives them from one measurement until the response data confirms it.

BCU module – Settings
Purpose. Configuration items transcribed from the supplied reference tool BCU → Settings screenshots. The values shown are the settings visible in this capture only. During protocol analysis, distinguish a read-settings request from any write/commit operation; do not assume that cycling a reference tool option immediately writes to the BCU.
BCU SETTINGS – LIGHTS WINDOWS-SEATS
#
reference tool label
Screenshot value
Test / changed setting
Request frame
Response frame
Candidate byte/bit / notes
1
Front fog lamp
NONE




2
Daytime run lights
NONE




3
Courtest head lamps
DISABLED




4
Headlamp power wash
NOT FITTED




5
Electric window front
DRV CANCE




6
Rear windows sunroof
DRV CANCE




7
Heated front screen
NOT FITTED




8
Electric front seats
NOT FITTED




9
Programmed wash wip
NORMAL




10
Seat belt warning
TIMED




11
Seat belt warning soun
TIMED




12
Autographics
ALWAYS




BCU SETTINGS – TRANSM-LOCK-WARN
#
reference tool label
Screenshot value
Test / changed setting
Request frame
Response frame
Candidate byte/bit / notes
1
Transmission
AUTO




2
Shift Interlock
NONE




3
HDC
NOT FITTED




4
Superlock
DISABLE




5
Single point entry
NOT SPE




6
Speed lock option
DISABLED




7
Mislock option
DISABLED




8
Bathrobe lock option
DISABLED




9
Odometer error warn
NOT FITTED




10
Key warning
DISABLED




11
Low battery warning
DISABLED




12
Bulb failure
DISABLED




BCU SETTINGS – INSTRUMENT PACK
Configuration items transcribed from the supplied reference tool BCU → Settings → Instrument Pack screenshots. One screenshot repeats the Gulf/Police/HDC/TRC page, so duplicate entries are listed only once.
#
reference tool label
Screenshot value
Test / changed setting
Request frame
Response frame
Candidate byte/bit / notes
1
Transmission
MANUAL




2
Engine
PETROL




3
ACE
YES




4
SLS
YES




5
Gulf
YES




6
Police
YES




7
HDC
YES




8
TRC
YES




Instrument Pack has several feature-presence flags (ACE, SLS, HDC, TRC, Gulf, Police) plus enumerated vehicle configuration such as Transmission and Engine. These are strong candidates for a packed configuration block; change only one setting at a time when mapping bytes/bits.
Notes for BCU settings protocol analysis
Preserve the displayed reference tool text exactly while mapping the protocol. Several labels/values are visibly abbreviated or appear misspelled in the UI (for example “Courtest head lamps”, “DRV CANCE”, “Seat belt warning soun” and “NOT SPE”). Do not expand these until the actual option semantics have been verified.
Settings are particularly useful for differential captures: read the same menu, change exactly one option in reference tool, read again, and compare the raw request/response frames. If possible, capture the traffic both when cycling the displayed value and when leaving/saving the menu.
Treat enumerated settings such as Transmission=AUTO, Programmed wash wip=NORMAL and Seat belt warning=TIMED as likely multi-valued fields rather than Boolean flags.
Before intentionally writing configuration, make a complete baseline capture of every settings page and record the original values so the BCU can be restored if needed.
BCU SETTINGS – ALARM-OTHER
#
reference tool label
Screenshot value
Test / changed setting
Request frame
Response frame
Candidate byte/bit / notes
1
Alarm
NOT FITTED




2
Alarm option
DISABLED




3
Alarm disarm
ALWAYS




4
Alarm sounder
ALARM




5
Alarm tamper
DISABLED




6
Engine immobil.
LED OFF




7
Passive immobil.
DISABLED




8
Inertia switch
NO HAZARD




9
Hazard option
DISABLED




10
Volumetric sensor
NOT FITTED




11
Market
UNKNOWN




12
EKA option
DISABLED




13
Cruise control
DISABLED




14
Air conditioning
NOT FITTED




15
Fuel burning heater
UNKNOWN




16
Passive coil
NOT FITTED




17
Transit mode
NOT SET




Protocol note. ALARM-OTHER contains a useful mixture of Boolean flags and enumerated fields (for example Alarm disarm, Alarm sounder, Inertia switch, Hazard option and Market). This makes the page especially useful for distinguishing packed bit fields from one-byte enumerations. In this captured screen Market is displayed as UNKNOWN; do not assign a market code until the raw response is mapped.
BCU INFO
#
reference tool label
Captured value
Test / changed setting
Request frame
Response frame
Candidate byte/bit / notes
1
Serial No
0




2
Date
11/02/02




3
Hardware No
1.01




4
Software No
8.02




5
Alarm Type
10




6
VIN
SAL + LTGA877A654321



UI shows prefix “SAL” separately from “LTGA877A654321”; concatenated form is SALLTGA877A654321.
Protocol note. The INFO page exposes six identity/version fields: Serial No, Date, Hardware No, Software No, Alarm Type and VIN. The values in the table are transcribed from the supplied screenshots. The VIN is displayed by reference tool in two adjacent fields (“SAL” and “LTGA877A654321”), which together form SALLTGA877A654321.
Reference cross-check. Menu labels were cross-checked against the official reference tool Valeo BCU (Discovery II) ECU guide; screenshot spellings remain the primary reference for reverse engineering.

BCU module – Outputs
BCU OUTPUTS – BODY
Protocol-order note. The sequence below is intentionally preserved exactly as presented in reference tool. Use the continuous Seq. number when analysing captures: the BODY outputs may be read or represented as one ordered block, so do not reorder items by function. Apparent duplicate or truncated labels are retained exactly from the UI.
Seq.
reference tool group
reference tool label
Available command
Request frame
Response frame
Candidate byte/bit / notes
1
LIGHTS
Front fog lights
ON / OFF



2
LIGHTS
Rear fog lights
ON / OFF



3
LIGHTS
Daytime running lights
ON / OFF



4
LIGHTS
LH indicator enable
ON / OFF



5
LIGHTS
LH indicator enable
ON / OFF



6
WINDOWS
Front left window up
ON / OFF



7
WINDOWS
Front left window down
ON / OFF



8
WINDOWS
Front right window up
ON / OFF



9
WINDOWS
Front right window dow
ON / OFF



10
WINDOWS
Rear windows enable
ON / OFF



11
WINDOWS
Sunroof enable
ON / OFF



12
WASH WIPE
Front wiper enable
ON / OFF



13
WASH WIPE
Tail wiper enable
ON / OFF



14
WASH WIPE
Head lamp power wash
ON / OFF



15
HEATED SCREEN
Heated screen
ENABLE / DISABLE



16
HEATED SCREEN
Heat. rear screen lamp
ON / OFF



17
CHECK ENGINE
Check engine lamp
ON / OFF



Capture strategy. For each output, capture the bus traffic before pressing a button, while issuing ON/ENABLE, and while issuing OFF/DISABLE. If reference tool first reads a complete BODY output-state block and then sends a separate command, keep both transactions in the log. The most useful first pass is to exercise items 1–17 strictly in sequence without navigating elsewhere.
UI anomalies to preserve. reference tool shows “LH indicator enable” twice in succession and truncates “Front right window dow”. These have deliberately not been corrected here. The second indicator entry may ultimately prove to be RH, but that should be established from traffic/vehicle behaviour rather than assumed.
BCU OUTPUTS – SECURITY
Protocol-order note. The SECURITY/LOCKING outputs below are listed in the exact top-to-bottom order shown by reference tool across the supplied screenshots. Keep this sequence intact when correlating captures. Treat this as a separate ordered output block from BODY unless the traffic proves they are returned by one common command.
Seq.
reference tool group
reference tool label
Available command
Request frame
Response frame
Candidate byte/bit / notes
1
SECURITY
Horn
ON / OFF



2
SECURITY
BBUS ALL
ON / OFF



3
SECURITY
BBUS ST
ON / OFF



4
SECURITY
Fuel flap
ON / OFF



5
SECURITY
Alarm LED
ON / OFF



6
SECURITY
Ignition interlock
ON / OFF



7
SECURITY
Crank Enable
ON / OFF



8
SECURITY
Volumetric power
ON / OFF



9
SECURITY
Robust immo.
ON / OFF



10
SECURITY
Transponder Power
ON / OFF



11
LOCKING
Lock
ON / OFF



12
LOCKING
Unlock
ON / OFF



13
LOCKING
Superlock
ON / OFF



14
LOCKING
Single point entry
ON / OFF



Capture strategy. Exercise SECURITY/LOCKING items 1–14 in this exact order. For each item, record the idle traffic, the frame(s) produced by ON, and the frame(s) produced by OFF. Locking, immobiliser and alarm-related outputs may cause state changes elsewhere in the BCU, so note extra unsolicited or follow-up traffic separately rather than assuming every changed byte belongs to the output command itself.
Ordering index. Outputs documented so far: BODY (17 ordered items) followed by SECURITY/LOCKING (14 ordered items). Do not merge or sort the two blocks by function during protocol analysis.
BCU UTILITIES – EKA CODE
Scope note. For now, only the two EKA-code operations shown in the Utilities menu are included: READ and SET. The four code fields are treated as one four-part EKA value; no assumptions are made yet about encoding, digit range, byte order, or whether READ and SET use related service identifiers.
Seq.
reference tool utility
Operation
Data / UI
Request frame
Response frame
Candidate service / payload / notes
1
EKA CODE
READ
Read current 4-part EKA code



2
EKA CODE
SET
Write 4-part EKA code



Capture priority. READ is the safe first target: capture the request and complete reply without changing vehicle configuration. SET should be sniffed only when intentionally writing a known-valid EKA code. Record all four displayed/entered values alongside the raw frame so their representation can be mapped directly.
BCU UTILITIES – KEY PROGRAMMING
Scope note. Included for completeness. Menu order and button order are preserved exactly because separate read/update/detect/synchronise operations may map to distinct protocol commands. Displayed values below are the values visible in the captured reference tool screens and should be treated as capture examples, not as assumed protocol constants.
Key codes / UPDATE
Seq.
reference tool field
Displayed value
Action
Request frame
Response frame
Candidate service / payload / notes
1
Key Code 1
2E85E2
SET



2
Key Code 2
220E02
SET



3
Key Code 3
F3B059
SET



4
Key Code 4
21DCF6
SET



5
Susp
111111
SET



6
—
—
UPDATE


Global update button shown below the five code rows
Key detection / synchronisation
Seq.
reference tool field
Displayed status
Action
Request frame
Response frame
Candidate service / payload / notes
1
Key 1
NOT DETECT.
SYNC



2
Key 2
NOT DETECT.
SYNC



3
Key 3
NOT DETECT.
SYNC



4
Key 4
NOT DETECT.
SYNC



5
SUSP
NOT DETECT.
SYNC



6
—
—
KEY DETECT


Global key-detection button shown below the five rows
Suspension plip BAR CODE
Seq.
reference tool item
Captured display / action
Request frame
Response frame
Candidate service / payload / notes
1
BAR CODE
*X11111111111X*


Transcribed from screenshot; verify exact number of 1 characters against a live capture before using it as protocol data.
2
—
SET CODE 1


Button
3
—
UPDATE


Button
Reverse-engineering note. Capture read/display traffic separately from each SET, UPDATE, KEY DETECT and SYNC action. For key-code programming, change only one known field at a time and keep the complete request/response sequence, including any acknowledgement or follow-up frame. This will make it possible to distinguish field identifiers from the six-hex-digit key-code payloads.
Verification log – 2026-08-08
Scope. The complete BCU material in this document was rechecked against the supplied reference tool screenshots. Menu order, labels and displayed capture values were preserved as shown, including apparent UI typos/truncations.
Corrected all 17 values/labels in Settings → ALARM-OTHER to match the screenshots.
Filled all six BCU INFO fields from the screenshots, including the split VIN display.
Replaced the previously incorrect Outputs → SECURITY list with the full 14-item SECURITY/LOCKING sequence shown in the screenshots.
Rechecked DCU Read Inputs, BCU Instruments, Power Distribution, Settings (Lights Windows-Seats, Transm-Lock-Warn, Instrument Pack), Outputs BODY, EKA Code and Key Programming against the supplied images; no additional transcription corrections were required.
No inferred “corrections” were made to reference tool UI anomalies such as duplicated “LH indicator enable”, truncated labels, or unusual spelling. These are retained because order and exact UI wording may help protocol mapping.

Additional modules - documentation roadmap
Modules to document next: ACE, Auto Gearbox, Airbag.
For these modules, preserve the reference tool menu order exactly. The working assumption is that each module follows the same broad structure below, but the exact commands and response layouts must be determined from captures rather than assumed.
Menu / function
Reverse-engineering note
Faults - Read
Read stored/current fault codes. Preserve display order and all text/codes exactly.
Faults - Clear
Clear faults. Record the request/response separately from Faults - Read.
Inputs
Live input/status values. Preserve exact reference tool order; this may map directly to byte/bit order in one returned block.
Outputs
Actuator/output tests. Preserve exact order and group boundaries shown by reference tool.
Utility
Module-specific service/programming/calibration functions. Document each function separately.
ACE
Status: Inputs, Outputs and Utility documented from reference tool screenshots; Faults still awaiting screenshots / captures.
Faults - Read
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Faults - Clear
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Inputs
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes
1
Engine Speed (rpm)




2
Road Speed (Km/h)




3
Battery Voltage (V)




4
DCV1 Current (AMP)




5
DCV2 Current (AMP)




6
PCV Current (AMP)




7
Pressure Sensor (bar)




8
Residual Pressure (bar)




9
System Pressure (bar)




10
Upper Lateral Acccelerometer




11
Lower Lateral Acccelerometer




12
Ignition Switch




13
Reverse Switch




14
Main Relay




15
Warning Lamp





Outputs
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes
1
Main relay(Force ON)
ON / STOP



2
Main relay(Force OFF)
OFF / STOP



3
Warning Lamp
ON / OFF



4
Dir. Control Valve 1
ON / OFF



5
Dir. Control Valve 2
ON / OFF



Protocol-order note. ACE Inputs and Outputs are recorded in the exact top-to-bottom order shown by reference tool. Preserve this sequence when correlating captures; the working hypothesis is that each menu may be read or controlled through a common command with fields returned or addressed in this order.

Utility
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes
1
Calib. Accelerometer 1
CALIBRATE



2
Calib. Accelerometer 2
CALIBRATE



3
Set Calibrated
SET



4
OIL BLEEDING STEP 1
START / STOP



5
OIL BLEEDING STEP 2
START / STOP



6
OIL BLEEDING STEP 3
START / STOP



Protocol-order note. Utility operations are kept in the exact reference tool menu order. Treat the three calibration operations and the three oil-bleeding steps as distinct commands until captures show otherwise. Bleeding functions are active procedures rather than passive reads, so capture the complete start/stop transaction and any periodic traffic generated while a step is running.

Auto Gearbox
Status: General Inputs documented from reference tool screenshots; Faults, Settings/other input groups, Outputs and Utility still awaiting screenshots / captures.
Faults - Read
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Faults - Clear
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Inputs
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes
1
Throttle position (%)




2
Engine torque (%)




3
Torque requested (%)




4
Reduced torque (%)




5
Friction torque (%)




6
Torque reference (Nm)




7
Gear switch W




8
Gear switch X




9
Gear switch Y




10
Gear switch Z




11
Program switch




12
High/Low range switch




13
Kick down




14
Shift type




15
Engine speed (RPM)




16
Turbine speed (RPM)




17
Output speed (RPM)




18
Battery (V)




19
Solenoid valve 1




20
Solenoid valve 2




21
Solenoid valve 3




22
Modulator pressure




23
Engine temperature (°C)




24
Adaptive program 1




25
Adaptive program 2




26
Adaptive program 3





Outputs
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Utility
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Airbag
Status: Settings documented from reference tool screenshots; Faults still awaiting screenshots / captures. This ECU is limited compared with the other Discovery 2 modules.
Faults - Read
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Faults - Clear
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Settings
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes
1
Manufacturer




2
Model




3
Software version




4
Hardware version




5
Serial number




6
Date of build




7
Part reference




8
Part number




9
VIN




10
Driver's airbag




11
Passenger's airbag




12
Right hand Pretensioner




13
Left hand Pretensioner




14
Driver's side airbag




15
Passenger's side airbag




16
Rolamites





Outputs
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Utility
#
reference tool label / function
Displayed value / options
Request frame
Response frame
Byte / bit / notes







Latest transcription notes - Auto Gearbox / Airbag
Auto Gearbox Inputs. The 26 GENERAL input items are kept in the supplied reference tool top-to-bottom sequence. Do not reorder them when correlating K-line captures. Treat the whole page as a possible single polling block until traffic proves otherwise.
Airbag Settings. The TRW SPS Type 2A ECU exposes identification/configuration data and only VIN is documented as programmable. Keep read-settings traffic separate from any VIN write operation. The settings order above is preserved as the working protocol order.
Airbag capability note. Unlike BCU/ACE, the Discovery 2 TRW SPS Type 2A is documented primarily for Read/Clear Faults and Settings; no separate live Inputs or Outputs page is assumed here unless a reference tool screen/capture demonstrates one.
```
