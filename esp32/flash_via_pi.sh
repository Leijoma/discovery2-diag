#!/bin/sh
# Flash the K-line node over the Pi's USB port (the node lives on discopi's USB in the car).
#
#   esp32/flash_via_pi.sh <pio build dir> [--full]
#
# <pio build dir> holds firmware.bin (+ bootloader.bin, partitions.bin), e.g. .pio/build/node.
# Default writes the app only: boot_app0.bin at 0xe000 + firmware at 0x10000. boot_app0 resets
# the OTA data partition, which matters: after an OTA update the node boots from app1
# (0x150000), so writing 0x10000 alone would be ignored. --full also writes the bootloader and
# partition table.
#
# On the Pi, /data/kline-relay/node-port takes the port from the relay (which closes it within
# ~1 s), runs the command with $NODE_PORT and esptool on PATH, and hands the port back on exit.
# esptool hard-resets the node via RTS afterwards.
set -eu
BUILD=${1:?usage: flash_via_pi.sh <pio build dir> [--full]}
FULL=${2:-}
PI=${PI_HOST:-discopi-wg}
BOOT_APP0=${BOOT_APP0:-$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin}
DEST=/tmp/kline-flash

FILES="$BOOT_APP0 $BUILD/firmware.bin"
ARGS="0xe000 $DEST/boot_app0.bin 0x10000 $DEST/firmware.bin"
if [ "$FULL" = "--full" ]; then
  FILES="$FILES $BUILD/bootloader.bin $BUILD/partitions.bin"
  ARGS="0x1000 $DEST/bootloader.bin 0x8000 $DEST/partitions.bin $ARGS"
fi
for f in $FILES; do [ -f "$f" ] || { echo "missing: $f" >&2; exit 1; }; done

ssh "$PI" "mkdir -p $DEST"
scp -q $FILES "$PI:$DEST/"
ssh "$PI" "/data/kline-relay/node-port sh -c 'esptool.py --chip esp32 --port \"\$NODE_PORT\" --baud 460800 write_flash $ARGS'"
