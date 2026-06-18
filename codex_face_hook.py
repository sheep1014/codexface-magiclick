import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

VALID_MODES = {
    "idle",
    "working",
    "attention",
    "blocked",
    "off",
}
ACTIVE_MODES = {
    "working",
    "attention",
    "blocked",
}
from codex_face_transport import send_command


LOG_PATH = Path.home() / ".codex" / "hooks" / "codex_face_hook.log"
LOCK_PATH = Path.home() / ".codex" / "hooks" / "codex_face_hook.lock"
STATE_PATH = Path.home() / ".codex" / "hooks" / "codex_face_hook_state.json"
DUPLICATE_WINDOW_SECONDS = 1.5
IDLE_DELAY_SECONDS = 4.0
TIMER_SENTINEL = "__idle_timer__"


def send_mode(mode: str) -> str:
    return send_command(mode)


def append_log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(mode: str, target: str, timestamp_value: float | None = None) -> None:
    payload = {
        "mode": mode,
        "target": target,
        "timestamp": time.time() if timestamp_value is None else timestamp_value,
    }
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def spawn_idle_timer(timestamp_value: float) -> None:
    try:
        subprocess.Popen(
            [sys.executable, __file__, TIMER_SENTINEL, str(timestamp_value)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        append_log(f"failed to spawn idle timer: {exc}")


def run_idle_timer(expected_timestamp: float) -> int:
    remaining = expected_timestamp + IDLE_DELAY_SECONDS - time.time()
    if remaining > 0:
        time.sleep(remaining)

    lock_fp = None
    try:
        if fcntl is not None:
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            lock_fp = LOCK_PATH.open("w", encoding="utf-8")
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)

        state = load_state()
        last_mode = state.get("mode")
        last_timestamp = float(state.get("timestamp", 0) or 0)
        if abs(last_timestamp - expected_timestamp) > 0.001:
            return 0
        if last_mode not in ACTIVE_MODES:
            return 0

        target = send_mode("idle")
        save_state("idle", target)
        append_log(f"auto-idle via {target}")
    except Exception as exc:
        append_log(f"auto-idle failed: {exc}")
    finally:
        if lock_fp is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
                lock_fp.close()
            except Exception:
                pass
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == TIMER_SENTINEL:
        try:
            return run_idle_timer(float(sys.argv[2]))
        except Exception as exc:
            append_log(f"idle timer crashed: {exc}")
            return 0

    mode = sys.argv[1] if len(sys.argv) > 1 else "idle"
    append_log(f"start mode={mode} python={sys.executable} script={__file__}")
    if mode not in VALID_MODES:
        append_log(f"ignored invalid mode: {mode}")
        return 0

    lock_fp = None
    try:
        if fcntl is not None:
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            lock_fp = LOCK_PATH.open("w", encoding="utf-8")
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)

        state = load_state()
        last_mode = state.get("mode")
        last_timestamp = float(state.get("timestamp", 0) or 0)
        if last_mode == mode and time.time() - last_timestamp < DUPLICATE_WINDOW_SECONDS:
            state_timestamp = time.time()
            save_state(mode, state.get("target", "duplicate"), state_timestamp)
            if mode in ACTIVE_MODES:
                spawn_idle_timer(state_timestamp)
            append_log(f"skipped duplicate {mode}")
            return 0

        target = send_mode(mode)
        state_timestamp = time.time()
        save_state(mode, target, state_timestamp)
        if mode in ACTIVE_MODES:
            spawn_idle_timer(state_timestamp)
        append_log(f"sent {mode} via {target}")
    except Exception as exc:
        append_log(f"failed {mode}: {exc}")
        return 0
    finally:
        if lock_fp is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
                lock_fp.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
