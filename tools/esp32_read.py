"""Read the ESP32 K-line sniffer's (kline_sniff.ino) USB serial + markers → log file.

    python3 tools/esp32_read.py [PORT] [outfile]

The ESP32 frames and timestamps by itself and sends hex rows @115200. This logs
them + lets you type **markers** in real time (text+Enter → `>>> ` row) so bytes can
be paired with the reference tool action (the read/clear cycle). ``q``+Enter quits.

Default port /dev/cu.usbserial-0001 (ESP32). NOTE: when the port opens the ESP32 may
auto-reset (it then prints its banner again) — completely normal.
"""
import os
import sys
import threading
import time

import serial

_lock = threading.Lock()
_stop = threading.Event()


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-0001"
    if len(sys.argv) > 2:
        outfile = sys.argv[2]
    else:
        os.makedirs("logs", exist_ok=True)
        outfile = os.path.join("logs", f"esp32_sniff-{time.strftime('%Y%m%d-%H%M%S')}.log")

    ser = serial.serial_for_url(port, baudrate=115200, timeout=0.2)
    fh = open(outfile, "a", encoding="utf-8")
    print(f"ESP32-sniff @ {port} → {outfile}")
    print("Type text+Enter = marker (e.g. 'SLABS read fault codes'). q+Enter = quit.")
    fh.write(f"=== SESSION {time.strftime('%Y-%m-%d %H:%M:%S')} — {port} ===\n")
    fh.flush()

    def reader():
        while not _stop.is_set():
            try:
                line = ser.readline()
            except serial.SerialException:
                break
            if line:
                s = line.decode("ascii", "replace").rstrip()
                with _lock:
                    print(s, flush=True)
                    fh.write(s + "\n")
                    fh.flush()

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    try:
        while True:
            try:
                m = input()
            except EOFError:
                break
            if m.strip().lower() in ("q", "quit", "exit"):
                break
            stamp = f">>> {m.strip() or '(marker)'}"
            with _lock:
                print(stamp, flush=True)
                fh.write(stamp + "\n")
                fh.flush()
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        th.join(timeout=1.0)
        with _lock:
            fh.write(f"=== END {time.strftime('%H:%M:%S')} ===\n")
            fh.close()
        ser.close()
    print(f"\ndone → {outfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
