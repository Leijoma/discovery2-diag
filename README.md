# Discovery 2 Td5 — Open Diagnostic Platform

En öppen, modulär diagnostikplattform för Land Rover Discovery 2 Td5. Målet är
inte ännu en OBD-läsare, utan ett **bibliotek** där Td5 är första
implementationen men arkitekturen håller för andra fordon och protokoll.

## Arkitektur

Strikt lagerindelning. Varje lager är frikopplat och byggs nerifrån och upp:

```
Td5        (seed/key ✓ · identifiers/datakonvertering kvar)          ← delvis
KWP2000    (10/27/3E/21 · negativa svar · responsePending)           ← implementerat
K-Line     (checksumma, ramformat adr+oadr, fast init, retries)      ← implementerat
Transport  (rå bytes in/ut — ingen protokollkunskap)                 ← implementerat
```

Td5:ans ramning: fast init är **adresserad** (`81 13 F7 81 0C`), resten av
sessionen **oadresserad** (`02 10 A0 B2`). Båda hanteras av ram-lagret.

Inget ovanför transportlagret vet *hur* bytesen färdas:

```python
from d2diag.transport import SerialTransport
transport = SerialTransport("/dev/ttyUSB0")   # 10400 baud, 8N1
# kwp = KWP2000(transport)                     # nästa lager
# td5 = Td5Engine(kwp)
```

## Var det körs

Biblioteket körs **på Raspberry Pi:n** (`signalK-test`, nås som `ssh pi`) där
USB KKL-kabeln sitter. Den seriella porten är därmed lokal, så den tidskänsliga
K-Line-trafiken (fast init, byte-timing) slipper ett nätverkshopp. Ingen
TCP-relä till en annan dator behövs.

- **Utveckling:** editeras på Mac (detta repo) / VS Code Remote-SSH, körs på Pi.
- **`TcpTransport`/brygga:** uppskjuten. Abstraktionen finns, men byggs bara om
  vi någon gång vill köra biblioteket från Mac mot icke-tidskänsliga tjänster.
- **Loggning:** `LoggingTransport` sparar all rå TX/RX med tidsstämpel till fil.

## Transportlagret (implementerat)

| Klass | Ansvar |
|---|---|
| `Transport` | Abstrakt bas: `open/close/send/receive` + context manager |
| `SerialTransport` | Seriell K-Line-adapter via pyserial. Testbar med `loop://` |
| `LoggingTransport` | Dekorerar en Transport, loggar TX/RX till fil |

`SerialTransport` exponerar även seriell lågnivåkontroll (`send_break`,
`baudrate`, `reset_input_buffer`) som *K-Line-lagret* kommer att använda för fast
init — aldrig lagren ovanför.

## Köra

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Testerna kör utan hårdvara via pyserials `loop://`-ekoport.

## Status

- [x] Transport (SerialTransport, LoggingTransport, tester)
- [x] K-Line (ramformat adresserat+oadresserat, checksumma, fast init, eko, timeout/retries)
- [x] KWP2000 (StartDiagnosticSession, TesterPresent, SecurityAccess, ReadDataByLocalIdentifier, negativa svar, responsePending)
- [~] Td5 (SecurityAccess seed→key ✓ · session ✓ · identifiers/skalning kvar)

Hårdvara under första utvecklingen: USB KKL 409.1 (FTDI FT232RL). Alla lager är
enhetstestade utan hårdvara mot en simulerad halv-duplex-ECU; den skarpa
verifieringen sker när kabeln sitter i bilen.

## Krediter och referenser

- **seed→key**: portad från [pajacobson/td5keygen](https://github.com/pajacobson/td5keygen) (BSD-2-Clause). Se [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
- **protokollreferens**: [EA2EGA/Ekaitza_Itzali](https://github.com/EA2EGA/Ekaitza_Itzali) (endast protokollfakta, ingen kod kopierad).
