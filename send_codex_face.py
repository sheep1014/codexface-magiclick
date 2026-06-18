#!/usr/bin/env python3
import sys
from codex_face_transport import send_command


VALID_MODES = ("idle", "working", "attention", "blocked", "off")


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

    target = send_command(command)

    print(f"Sent '{command}' -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
