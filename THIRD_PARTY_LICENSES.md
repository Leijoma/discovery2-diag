# Third-party licenses and sources

## td5keygen — SecurityAccess seed→key

`src/d2diag/td5/keygen.py` is a Python port of the algorithm in
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

## Ekaitza_Itzali — protocol reference (no code used)

[EA2EGA/Ekaitza_Itzali](https://github.com/EA2EGA/Ekaitza_Itzali) has been used as a
**reference for protocol facts** (frame format, ECU addresses, init sequence,
identifiers + scaling, plus the fault-code map for `21 3B` — offset/bitmask →
fault text, which are facts about the ECU's diagnostics). No source code from there is
copied — the repo has no license, so only non-protectable facts about the protocol have been used.
The init/session/security/fault-code sequences are moreover verified against the repo's
sniff logs (`Sniffing/*.log`). Credits in that project go to OffTrack
(ECU disassembly) and Luca72 (Arduino reference).

The Td5 fault-code map (`21 3B`) is additionally **cross-validated against a public,
community-spread list of Td5 fault codes** — same names on the same offset/bit,
which also yielded the more precise status distinction Logged Low / Logged High /
Current. Only factual data (offset/bit → fault text) has been used.

## BinOwl_Td5Gauge — protocol reference (GPL-3.0, no code used)

[k0sci3j/BinOwl_Td5Gauge](https://github.com/k0sci3j/BinOwl_Td5Gauge) — an ESP32 Td5
gauge, **GPL-3.0**. Reviewed 2026-08-25 as a **reference for protocol facts only**
(LID -> field offsets and scalings, frame lengths, init/keepalive sequence); see
`references/td5_externa_fynd.md`. GPL-3.0 is incompatible with this project, so
**no source code from there may be copied or ported** — only non-protectable facts
about the ECU protocol, each of which is verified against our own captures before use.

## muki01/OBD2_K-line_Reader — K-line reference (MIT)

[muki01/OBD2_K-line_Reader](https://registry.platformio.org/libraries/muki01/OBD2%20K-Line)
— OBD2 K-line library (ISO 9141 / ISO 14230) for Arduino/ESP32, **MIT license**.
An archived copy (Basic_Code + Schematics) is in `references/muki01_OBD2_K-line_Reader/`
as a reference for the ESP32 port (fast init timing, burst reading, L9637D interface). MIT
allows reuse with the copyright and license notice retained; keep this
attribution if code from there is ported in.

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
