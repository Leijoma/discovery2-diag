# Tredjepartslicenser och källor

## td5keygen — SecurityAccess seed→key

`src/d2diag/td5/keygen.py` är en Python-port av algoritmen i
[pajacobson/td5keygen](https://github.com/pajacobson/td5keygen).

> BSD 2-Clause License
>
> Copyright (c) 2017, paul@discotd5.com
> Python-variant (keytool.py): Copyright (c) 2017, xabiergarmendia@gmail.com
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this
>    list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
> ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
> WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
> ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
> (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
> LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
> ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
> (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
> SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Ekaitza_Itzali — protokollreferens (ingen kod använd)

[EA2EGA/Ekaitza_Itzali](https://github.com/EA2EGA/Ekaitza_Itzali) har använts som
**referens för protokollfakta** (ramformat, ECU-adresser, init-sekvens,
identifiers + skalning, samt felkodskartan för `21 3B` — offset/bitmask →
feltext, som är fakta om ECU:ns diagnostik). Ingen källkod därifrån är kopierad —
repot saknar licens, så endast icke-skyddbara fakta om protokollet har använts.
Init-/session-/security-/felkodssekvenserna är dessutom verifierade mot repots
sniff-loggar (`Sniffing/*.log`). Krediter i det projektet till OffTrack
(ECU-disassembly) och Luca72 (Arduino-referens).

## muki01/OBD2_K-line_Reader — K-line-referens (MIT)

[muki01/OBD2_K-line_Reader](https://registry.platformio.org/libraries/muki01/OBD2%20K-Line)
— OBD2 K-line-bibliotek (ISO 9141 / ISO 14230) för Arduino/ESP32, **MIT-licens**.
En arkiverad kopia (Basic_Code + Schematics) finns i `references/muki01_OBD2_K-line_Reader/`
som referens för ESP32-porten (fast init-timing, burst-läsning, L9637D-interface). MIT
tillåter återanvändning med bibehållen upphovsrätts- och licensnotis; behåll denna
attribution om kod därifrån portas in.
