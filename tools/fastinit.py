"""Kör fast init + StartCommunication mot en riktig KKL-kabel och logga TX/RX.

    # på Pi:n (venv med d2diag installerat):
    python tools/fastinit.py /dev/ttyUSB0

    # på Mac (från repo-roten):
    PYTHONPATH=src python3 tools/fastinit.py /dev/cu.usbserial-12345678

Kräver bilen ansluten (OBD) och tändning på — annars timeout (ingen ECU på linjen).
"""
import sys

from d2diag.kline import KLine, KLineError
from d2diag.transport import LoggingTransport, SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    print(f"Öppnar {port} @ 10400 8N1, kör fast init …")
    transport = LoggingTransport(SerialTransport(port, timeout=1.0), echo=True)
    with KLine(transport) as k:
        try:
            data = k.fast_init()
        except KLineError as exc:
            print(f"Ingen kontakt: {exc}")
            return 1
    print(f"Svar: {data.hex(' ')}")
    if data[:1] == b"\xc1":
        print(f"POSITIVT StartCommunication — nyckelbytes {data[1:].hex(' ')}")
        print("ECU:n i diag-läge. Nästa: StartDiagnosticSession (10 A0) + identifiers.")
    elif data[:1] == b"\x7f":
        nrc = data[2] if len(data) > 2 else 0
        print(f"Negativt (NRC 0x{nrc:02X}) — troligen redan i session; "
              "vänta ut timeouten (~5 s) och kör igen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
