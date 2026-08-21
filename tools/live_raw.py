"""Permissive Td5 reading (muki01-style) for a noisy KKL cable.

Reads the whole response burst until ~60 ms of silence, picks values at fixed
positions and does NOT reject on checksum (better a value to verify than nothing).
Uses baud-drop init and the Td5 scaling from d2diag.td5.identifiers.

    PYTHONPATH=src python3 tools/live_raw.py /dev/cu.usbserial-XXXX

Run with ignition on but the engine OFF.
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

    # ---- fast init until 0xC1 appears in the burst ----
    ok = False
    for i in range(15):
        ser.reset_input_buffer()
        _fast_init_low(ser)
        time.sleep(0.025)
        raw = _burst(ser, bytes([0x81, 0x13, 0xF7, 0x81, 0x0C]))
        if 0xC1 in raw:
            print(f"init {i + 1}: C1 (session open)  raw={raw.hex(' ')}")
            ok = True
            break
        print(f"init {i + 1}: {raw.hex(' ') or 'empty'}")
    if not ok:
        print("Could not open session (no C1).")
        return 1

    # ---- StartDiagnosticSession 10 A0 ----
    raw = _burst(ser, _frame(bytes([0x02, 0x10, 0xA0])))
    print(f"StartDiagnosticSession raw={raw.hex(' ')}\n--- live data (permissive) ---")

    # ---- read known LIDs ----
    for lid in LIDS:
        raw = _burst(ser, _frame(bytes([0x02, 0x21, lid])))
        # the response: find positive SID 0x61 followed by the echoed LID; data follows
        idx = raw.find(bytes([0x61, lid]))
        data = raw[idx + 2:] if idx >= 0 else b""
        marker = "" if idx >= 0 else "  (no 61 response found)"
        print(f"21 {lid:02X}  raw={raw.hex(' ')}{marker}")
        for sig in signals_for_lid(lid):
            if sig.fits(data):
                print(f"    {sig.name:16} {sig.decode(data):9.2f} {sig.unit}")
        time.sleep(0.05)

    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
