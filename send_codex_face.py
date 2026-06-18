#!/usr/bin/env python3
import glob
import os
import sys
import time

import serial


VALID_MODES = ("idle", "working", "attention", "blocked", "off")
BAUD = 115200
DEFAULT_PORT = "/dev/cu.usbmodem42CEA4F10A401"


def find_port() -> str:
    configured = os.environ.get("MAGICLICK_PORT") or os.environ.get("CODEX_FACE_PORT")
    if configured:
        return configured

    if os.path.exists(DEFAULT_PORT):
        return DEFAULT_PORT

    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if ports:
        return ports[0]

    raise FileNotFoundError("No MagiClick serial port found")


def build_command(argv):
    if len(argv) == 2 and argv[1] in VALID_MODES:
        return argv[1]

    if len(argv) >= 3 and argv[1] == "--text":
        return "text " + " ".join(argv[2:])

    if len(argv) == 2 and argv[1] == "--clear":
        return "cleartext"

    return None


def main() -> int:
    command = build_command(sys.argv)
    if not command:
        modes = ", ".join(VALID_MODES)
        print(
            f"Usage: {sys.argv[0]} <{modes}> | --text <message> | --clear",
            file=sys.stderr,
        )
        return 2

    port = find_port()
    with serial.Serial(port, BAUD, timeout=0.5, write_timeout=0.5) as ser:
        time.sleep(0.25)
        ser.write((command + "\n").encode("utf-8"))
        ser.flush()

    print(f"Sent '{command}' -> {port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
