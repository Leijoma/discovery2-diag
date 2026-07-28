"""Permissiv Td5-avläsning (muki01-stil) för brusig KKL-kabel.

Läser hela svarsbursten tills ~60 ms tystnad, plockar värden på fixa positioner
och avvisar INTE på checksumma (får hellre ett värde att verifiera än inget).
Använder baud-drop-init och Td5-skalningen från d2diag.td5.identifiers.

    PYTHONPATH=src python3 tools/live_raw.py /dev/cu.usbserial-XXXX

Kör med tändning på men motorn AV.
"""
import sys
import time

import serial

from d2diag.td5.identifiers import LIDS, signals_for_lid


def _checksum(b: bytes) -> int:
    return sum(b) & 0xFF


def _burst(ser, frame: bytes, gap: float = 0.06, overall: float = 1.2) -> bytes:
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    buf = bytearray()
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < overall:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            last = time.monotonic()
        elif last is not None and time.monotonic() - last > gap:
            break
        else:
            time.sleep(0.002)
    return bytes(buf)


def _fast_init_low(ser, low: float = 0.025) -> None:
    orig = ser.baudrate
    ser.baudrate = round(9 / low)
    ser.write(b"\x00")
    ser.flush()
    ser.baudrate = orig
    ser.reset_input_buffer()


def _frame(data: bytes) -> bytes:
    return data + bytes([_checksum(data)])


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    ser = serial.serial_for_url(
        port, baudrate=10400, bytesize=8, parity="N", stopbits=1, timeout=0.05
    )

    # ---- fast init tills 0xC1 dyker upp i bursten ----
    ok = False
    for i in range(15):
        ser.reset_input_buffer()
        _fast_init_low(ser)
        time.sleep(0.025)
        raw = _burst(ser, bytes([0x81, 0x13, 0xF7, 0x81, 0x0C]))
        if 0xC1 in raw:
            print(f"init {i + 1}: C1 (session öppen)  raw={raw.hex(' ')}")
            ok = True
            break
        print(f"init {i + 1}: {raw.hex(' ') or 'tomt'}")
    if not ok:
        print("Kunde inte öppna session (ingen C1).")
        return 1

    # ---- StartDiagnosticSession 10 A0 ----
    raw = _burst(ser, _frame(bytes([0x02, 0x10, 0xA0])))
    print(f"StartDiagnosticSession raw={raw.hex(' ')}\n--- livedata (permissiv) ---")

    # ---- läs kända LID:er ----
    for lid in LIDS:
        raw = _burst(ser, _frame(bytes([0x02, 0x21, lid])))
        # svaret: hitta positivt SID 0x61 följt av ekad LID; data följer
        idx = raw.find(bytes([0x61, lid]))
        data = raw[idx + 2:] if idx >= 0 else b""
        marker = "" if idx >= 0 else "  (inget 61-svar hittat)"
        print(f"21 {lid:02X}  raw={raw.hex(' ')}{marker}")
        for sig in signals_for_lid(lid):
            if sig.fits(data):
                print(f"    {sig.name:16} {sig.decode(data):9.2f} {sig.unit}")
        time.sleep(0.05)

    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
