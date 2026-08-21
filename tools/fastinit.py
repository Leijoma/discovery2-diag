"""Run fast init + StartCommunication against a real KKL cable and log TX/RX.

    # on the Pi (venv with d2diag installed):
    python tools/fastinit.py /dev/ttyUSB0

    # on a Mac (from the repo root):
    PYTHONPATH=src python3 tools/fastinit.py /dev/cu.usbserial-12345678

Requires the car connected (OBD) and ignition on — otherwise timeout (no ECU on the line).
"""
import sys

from d2diag.kline import KLine, KLineError
from d2diag.transport import LoggingTransport, SerialTransport


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    print(f"Opening {port} @ 10400 8N1, running fast init …")
    transport = LoggingTransport(SerialTransport(port, timeout=1.0), echo=True)
    with KLine(transport) as k:
        try:
            data = k.fast_init()
        except KLineError as exc:
            print(f"No contact: {exc}")
            return 1
    print(f"Response: {data.hex(' ')}")
    if data[:1] == b"\xc1":
        print(f"POSITIVE StartCommunication — key bytes {data[1:].hex(' ')}")
        print("ECU in diag mode. Next: StartDiagnosticSession (10 A0) + identifiers.")
    elif data[:1] == b"\x7f":
        nrc = data[2] if len(data) > 2 else 0
        print(f"Negative (NRC 0x{nrc:02X}) — probably already in a session; "
              "wait out the timeout (~5 s) and run again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
