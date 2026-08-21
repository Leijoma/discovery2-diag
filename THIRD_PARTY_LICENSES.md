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

Td5-felkodskartan (`21 3B`) är dessutom **korsvaliderad mot en publik,
community-spridd lista över Td5-felkoder** — samma namn på samma offset/bit,
vilket också gav den mer precisa statusdistinktionen Logged Low / Logged High /
Current. Endast faktauppgifter (offset/bit → feltext) har använts.

## muki01/OBD2_K-line_Reader — K-line-referens (MIT)

[muki01/OBD2_K-line_Reader](https://registry.platformio.org/libraries/muki01/OBD2%20K-Line)
— OBD2 K-line-bibliotek (ISO 9141 / ISO 14230) för Arduino/ESP32, **MIT-licens**.
En arkiverad kopia (Basic_Code + Schematics) finns i `references/muki01_OBD2_K-line_Reader/`
som referens för ESP32-porten (fast init-timing, burst-läsning, L9637D-interface). MIT
tillåter återanvändning med bibehållen upphovsrätts- och licensnotis; behåll denna
attribution om kod därifrån portas in.

## Astryx — UI theme tokens (dashboard visual design)

The web dashboard's neutral colour/spacing tokens are adapted from
[facebook/astryx](https://astryx.atmeta.com/) (`packages/themes/neutral`), Meta's
open-source design system, **MIT-licensed**. Only the theme token *values* (colours,
radii, spacing) are used, inlined as CSS custom properties in `dashboard_v2.html` and
kept in `ui/astryx-theme.css`.

> MIT License
>
> Copyright (c) Meta Platforms, Inc. and affiliates.
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in the
> Software without restriction, including without limitation the rights to use, copy,
> modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
> and to permit persons to whom the Software is furnished to do so, subject to the
> following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
> INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
> PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
> HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
> CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
> OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The Figtree font is loaded from Google Fonts (SIL Open Font License).
