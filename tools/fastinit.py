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
    print(f"StartCommunication-svar: {data.hex(' ')}")
    print("Kontakt med ECU:n! Nästa steg: StartDiagnosticSession + identifiers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
