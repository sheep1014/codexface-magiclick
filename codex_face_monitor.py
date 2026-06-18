#!/usr/bin/env python3
import subprocess
import time

from codex_face_hook import send_mode


CODEX_MAIN_PROCESS = "/Applications/Codex.app/Contents/MacOS/Codex"


def codex_is_running() -> bool:
    result = subprocess.run(
        ["/bin/ps", "-axo", "args"],
        capture_output=True,
        text=True,
        timeout=2,
    )
    if result.returncode != 0:
        return False

    for line in result.stdout.splitlines():
        if line.strip() == CODEX_MAIN_PROCESS:
            return True
    return False


def main() -> int:
    last_state = None
    while True:
        running = codex_is_running()
        if running != last_state:
            try:
                send_mode("idle" if running else "off")
            except Exception:
                pass
            last_state = running
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
