#!/usr/bin/env python3
import glob
import os
import sys
import time

import serial


BAUD = 115200
DEFAULT_PORT = "/dev/cu.usbmodem42CEA4F10A401"
VALID_MODES = {
    "idle",
    "working",
    "attention",
    "blocked",
    "off",
}


def find_port() -> str:
    configured = os.environ.get("CODEX_FACE_PORT") or os.environ.get("MAGICLICK_PORT")
    if configured:
        return configured

    if os.path.exists(DEFAULT_PORT):
        return DEFAULT_PORT

    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if ports:
        return ports[0]

    raise FileNotFoundError("No MagiClick serial port found")


def send_mode(mode: str) -> None:
    port = find_port()
    with serial.Serial(port, BAUD, timeout=0.5, write_timeout=0.5) as ser:
        time.sleep(0.25)
        ser.write((mode + "\n").encode("utf-8"))
        ser.flush()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "idle"
    if mode not in VALID_MODES:
        return 0

    try:
        send_mode(mode)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
