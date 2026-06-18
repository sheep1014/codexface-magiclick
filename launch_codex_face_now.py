#!/usr/bin/env python3
import glob
import os
import time

import serial


BAUD = 115200
DEFAULT_PORT = "/dev/cu.usbmodem42CEA4F10A401"
SCRIPT = (
    'import supervisor\n'
    'supervisor.set_next_code_file("/app/CodexFace.py")\n'
    "supervisor.reload()\n"
)


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


def read_until(ser, marker: bytes, timeout: float = 3.0) -> bytes:
    end = time.time() + timeout
    data = bytearray()
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            data.extend(chunk)
            if marker in data:
                return bytes(data)
    return bytes(data)


def enter_friendly_repl(ser) -> None:
    ser.reset_input_buffer()
    ser.write(b"\x03\x03\x02")
    ser.flush()
    out = read_until(ser, b">>> ", 3.0)
    if b">>> " not in out and b"Press any key to enter the REPL" in out:
        ser.write(b"\x02")
        ser.flush()
        out += read_until(ser, b">>> ", 2.0)
    if b">>> " not in out:
        raise RuntimeError(f"Failed to enter REPL: {out!r}")


def enter_paste_mode(ser) -> None:
    for _ in range(3):
        ser.reset_input_buffer()
        ser.write(b"\x05")
        ser.flush()
        out = read_until(ser, b"=== ", 2.0)
        if b"paste mode" in out:
            return
    raise RuntimeError(f"Failed to enter paste mode: {out!r}")


def main() -> int:
    port = find_port()
    with serial.Serial(port, BAUD, timeout=0.5, write_timeout=0.5) as ser:
        time.sleep(0.2)
        enter_friendly_repl(ser)
        enter_paste_mode(ser)

        ser.write(SCRIPT.encode("utf-8"))
        ser.write(b"\x04")
        ser.flush()
        time.sleep(0.8)
        output = ser.read(4096).decode("utf-8", "ignore")

    if "/app/CodexFace.py output:" not in output and "soft reboot" not in output:
        raise RuntimeError(f"Board did not confirm app launch: {output!r}")

    print(f"Launched CodexFace on {port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
