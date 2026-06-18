#!/usr/bin/env python3
import base64
import glob
import os
import shutil
import sys
import time
from pathlib import Path

import serial


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "codex_status.py"
MOUNT = Path("/Volumes/CIRCUITPY")
DEST_RELATIVE = Path("app/CodexFace.py")
DEST = "/" + DEST_RELATIVE.as_posix()
BACKUP_DIR = ROOT / "backups"
DEFAULT_PORT = "/dev/cu.usbmodem42CEA4F10A401"
BLE_LIB_ROOT = ROOT / "vendor" / "circuitpython9" / "lib"
BLE_LIB_KEEP = {
    "adafruit_ble/__init__.mpy",
    "adafruit_ble/advertising/__init__.mpy",
    "adafruit_ble/advertising/standard.mpy",
    "adafruit_ble/attributes/__init__.mpy",
    "adafruit_ble/characteristics/__init__.mpy",
    "adafruit_ble/characteristics/stream.mpy",
    "adafruit_ble/services/__init__.mpy",
    "adafruit_ble/services/nordic.mpy",
    "adafruit_ble/uuid/__init__.mpy",
}
APP_PATH = "/app/CodexFace.py"


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def find_port() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]

    configured = os.environ.get("MAGICLICK_PORT") or os.environ.get("CODEX_FACE_PORT")
    if configured:
        return configured

    if os.path.exists(DEFAULT_PORT):
        return DEFAULT_PORT

    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    if ports:
        return ports[0]

    raise FileNotFoundError("No MagiClick serial port found")


def copy_via_mount() -> Path:
    board_dest = MOUNT / DEST_RELATIVE
    board_dest.parent.mkdir(parents=True, exist_ok=True)

    if board_dest.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f"live-CodexFace-{timestamp()}.py"
        shutil.copy2(board_dest, backup_path)
        print(f"Backed up live app to {backup_path}")

    shutil.copy2(SOURCE, board_dest)
    print(f"Copied {SOURCE.name} -> {board_dest}")
    copy_tree_via_mount(BLE_LIB_ROOT / "adafruit_ble", MOUNT / "lib" / "adafruit_ble")
    return board_dest


def copy_tree_via_mount(src_root: Path, dest_root: Path) -> None:
    for local_path in sorted(src_root.rglob("*")):
        relative_from_lib = local_path.relative_to(BLE_LIB_ROOT).as_posix()
        if local_path.is_file() and relative_from_lib not in BLE_LIB_KEEP:
            continue
        relative = local_path.relative_to(src_root)
        board_path = dest_root / relative
        if local_path.is_dir():
            board_path.mkdir(parents=True, exist_ok=True)
            continue
        board_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, board_path)
        print(f"Copied {local_path.relative_to(ROOT)} -> {board_path}")


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


def enter_raw_repl(ser) -> None:
    attempts = (
        b"\x02",
        b"\r\x03\x03\x02",
        b"\r\x02",
    )
    last_out = b""
    for prefix in attempts:
        ser.reset_input_buffer()
        ser.write(prefix)
        ser.flush()
        time.sleep(0.25)
        ser.read(512)
        ser.write(b"\x01")
        ser.flush()
        out = read_until(ser, b">", 2.0)
        if b"raw REPL" in out:
            return
        last_out = out
    raise RuntimeError(f"Failed to enter raw REPL: {last_out!r}")


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


def exec_paste(ser, script: str, timeout: float = 6.0) -> str:
    ser.reset_input_buffer()
    ser.write(b"\x05")
    ser.flush()
    out = read_until(ser, b"=== ", 2.0)
    if b"paste mode" not in out:
        raise RuntimeError(f"Failed to enter paste mode: {out!r}")

    payload = script.encode("utf-8")
    for offset in range(0, len(payload), 128):
        ser.write(payload[offset : offset + 128])
        ser.flush()
        time.sleep(0.01)
    ser.write(b"\x04")
    ser.flush()

    data = read_until(ser, b">>> ", timeout)
    if b">>> " not in data:
        raise RuntimeError(f"Paste execution did not finish: {data!r}")
    text = data.decode("utf-8", "ignore")
    if "Traceback (most recent call last):" in text:
        raise RuntimeError(text)
    return text


def exec_raw(ser, script: str, timeout: float = 6.0, enter: bool = True) -> str:
    if enter:
        enter_raw_repl(ser)
    ser.write(script.encode("utf-8"))
    ser.write(b"\x04")
    ser.flush()
    ok = read_until(ser, b"OK", 2.0)
    if b"OK" not in ok:
        raise RuntimeError(f"Board did not acknowledge script: {ok!r}")

    end = time.time() + timeout
    data = bytearray()
    while time.time() < end:
        chunk = ser.read(512)
        if chunk:
            data.extend(chunk)
            if data.endswith(b"\x04>"):
                break
        else:
            time.sleep(0.05)

    raw = bytes(data)
    raw = raw[:-2] if raw.endswith(b"\x04>") else raw
    if b"\x04" in raw:
        stdout, stderr = raw.split(b"\x04", 1)
    else:
        stdout, stderr = raw, b""
    if stderr.strip():
        raise RuntimeError(stderr.decode("utf-8", "ignore"))
    return stdout.decode("utf-8", "ignore")


def copy_via_raw_repl(port: str) -> None:
    uploads = [("/" + DEST_RELATIVE.as_posix(), SOURCE)]
    uploads.extend(iter_ble_lib_uploads())

    with serial.Serial(port, 115200, timeout=0.4, write_timeout=1) as ser:
        enter_friendly_repl(ser)
        enable_local_writes(ser)
        disable_autoreload(ser)
        ensure_board_dirs(ser)
        for board_path, local_path in uploads:
            upload_file_via_raw_repl(ser, local_path, board_path)
        try:
            exec_paste(
                ser,
                "import supervisor\n"
                f"supervisor.set_next_code_file({APP_PATH!r})\n"
                "supervisor.reload()\n",
                timeout=3.0,
            )
        except Exception:
            pass


def activate_installed_app(port: str) -> None:
    with serial.Serial(port, 115200, timeout=0.4, write_timeout=1) as ser:
        enter_friendly_repl(ser)
        try:
            exec_paste(
                ser,
                "import supervisor\n"
                f"supervisor.set_next_code_file({APP_PATH!r})\n"
                "print('NEXT_OK')\n"
                "supervisor.reload()\n",
                timeout=4.0,
            )
        except RuntimeError as exc:
            # A successful reload exits before friendly REPL returns.
            message = str(exc)
            if "Paste execution did not finish:" not in message and "soft reboot" not in message:
                raise


def iter_ble_lib_uploads():
    src_root = BLE_LIB_ROOT / "adafruit_ble"
    for local_path in sorted(src_root.rglob("*")):
        if local_path.is_file():
            relative = local_path.relative_to(BLE_LIB_ROOT)
            if relative.as_posix() not in BLE_LIB_KEEP:
                continue
            yield ("/lib/" + relative.as_posix(), local_path)


def ensure_board_dirs(ser) -> None:
    directories = {
        "/app",
        "/lib",
        "/lib/adafruit_ble",
        "/lib/adafruit_ble/advertising",
        "/lib/adafruit_ble/attributes",
        "/lib/adafruit_ble/characteristics",
        "/lib/adafruit_ble/services",
        "/lib/adafruit_ble/services/standard",
        "/lib/adafruit_ble/uuid",
    }
    script = (
        "import os\n"
        "for path in " + repr(sorted(directories)) + ":\n"
        "    try:\n"
        "        os.mkdir(path)\n"
        "    except OSError:\n"
        "        pass\n"
        "print('DIRS_READY')\n"
    )
    exec_paste(ser, script, timeout=4.0)


def disable_autoreload(ser) -> None:
    script = (
        "import supervisor\n"
        "try:\n"
        "    supervisor.runtime.autoreload = False\n"
        "except AttributeError:\n"
        "    try:\n"
        "        supervisor.disable_autoreload()\n"
        "    except AttributeError:\n"
        "        pass\n"
        "print('AUTORELOAD_OFF')\n"
    )
    exec_paste(ser, script, timeout=4.0)


def enable_local_writes(ser) -> None:
    script = (
        "import storage\n"
        "storage.remount('/', readonly=False)\n"
        "print('LOCAL_WRITES_ON')\n"
    )
    exec_paste(ser, script, timeout=4.0)


def upload_file_via_raw_repl(ser, local_path: Path, board_path: str) -> None:
    print(f"Uploading {local_path.relative_to(ROOT)} -> {board_path}")
    data = local_path.read_bytes()
    chunk_size = 256
    chunks = [
        base64.b64encode(data[offset : offset + chunk_size]).decode("ascii")
        for offset in range(0, len(data), chunk_size)
    ]
    script = (
        "import binascii, os\n"
        "chunks = %r\n"
        "with open(%r, 'wb') as fp:\n"
        "    for chunk in chunks:\n"
        "        fp.write(binascii.a2b_base64(chunk))\n"
        "print('WROTE', %r, os.stat(%r)[6])\n"
    ) % (chunks, board_path, board_path, board_path)
    timeout = max(6.0, len(script) / 1500.0)
    output = exec_paste(ser, script, timeout=timeout)
    if output.strip():
        print(output.strip())


def print_next_steps(reason: str) -> None:
    print()
    print("Install did not complete.")
    print(f"Reason: {reason}")
    print()
    print("Next steps:")
    print("1. Replug the board and check whether /Volumes/CIRCUITPY becomes writable.")
    print("2. If it still mounts read-only, enter CircuitPython safe mode once and try again.")
    print("3. If the serial REPL starts responding, rerun this script and it can install over USB.")


def main() -> int:
    mount_error = None
    if MOUNT.exists():
        try:
            copy_via_mount()
            try:
                port = find_port()
                activate_installed_app(port)
                print(f"Activated {APP_PATH} on {port}")
            except Exception as exc:
                print(f"Installed files, but could not auto-launch {APP_PATH}: {exc}")
            return 0
        except OSError as exc:
            mount_error = exc
            print(f"Mount copy skipped: {exc}")

    try:
        port = find_port()
    except Exception as exc:
        print_next_steps(str(mount_error or exc))
        return 1

    try:
        copy_via_raw_repl(port)
        try:
            activate_installed_app(port)
            print(f"Activated {APP_PATH} on {port}")
        except Exception as exc:
            print(f"Installed via raw REPL, but could not auto-launch {APP_PATH}: {exc}")
        print(f"Installed via raw REPL on {port}")
        return 0
    except Exception as exc:
        reason = str(exc)
        if mount_error:
            reason = f"{mount_error}; raw REPL also failed: {exc}"
        print_next_steps(reason)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
