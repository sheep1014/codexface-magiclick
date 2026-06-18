#!/usr/bin/env python3
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "codex_hooks_template.json"
SOURCE_HOOK = ROOT / "codex_face_hook.py"
TARGET_DIR = Path.home() / ".codex" / "hooks"
TARGET_HOOK = TARGET_DIR / "agent_face_hook.py"
TARGET_CONFIG = Path.home() / ".codex" / "hooks.json"


def main() -> int:
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Missing template: {TEMPLATE}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_HOOK, TARGET_HOOK)

    content = TEMPLATE.read_text(encoding="utf-8")
    content = content.replace("__PYTHON__", sys.executable)
    content = content.replace("__HOOK__", str(TARGET_HOOK))
    data = json.loads(content)

    if TARGET_CONFIG.exists():
        backup = TARGET_CONFIG.with_name("hooks.backup.json")
        shutil.copy2(TARGET_CONFIG, backup)
        print(f"Backed up existing hooks config to {backup}")

    TARGET_CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Installed hook script to {TARGET_HOOK}")
    print(f"Wrote Codex hooks config to {TARGET_CONFIG}")
    print("If your board uses a non-default serial path, set CODEX_FACE_PORT or MAGICLICK_PORT first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

