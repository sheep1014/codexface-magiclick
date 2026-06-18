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
MIN_ACTIVE_DISPLAY_SECONDS = 3.0
LONG_WORKING_SECONDS = 10.0
IDLE_TIMER_SENTINEL = "__idle_timer__"
ATTENTION_TIMER_SENTINEL = "__attention_timer__"


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


def save_state(
    mode: str,
    target: str,
    timestamp_value: float | None = None,
    active_since: float | None = None,
) -> None:
    stamp = time.time() if timestamp_value is None else timestamp_value
    payload = {
        "mode": mode,
        "target": target,
        "timestamp": stamp,
    }
    if active_since is not None:
        payload["active_since"] = active_since
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def spawn_attention_timer(active_since: float) -> None:
    try:
        subprocess.Popen(
            [sys.executable, __file__, ATTENTION_TIMER_SENTINEL, str(active_since)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        append_log(f"failed to spawn attention timer: {exc}")


def spawn_idle_timer(expected_timestamp: float) -> None:
    try:
        subprocess.Popen(
            [sys.executable, __file__, IDLE_TIMER_SENTINEL, str(expected_timestamp)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        append_log(f"failed to spawn idle timer: {exc}")


def run_idle_timer(expected_timestamp: float) -> int:
    remaining = expected_timestamp + MIN_ACTIVE_DISPLAY_SECONDS - time.time()
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


def run_attention_timer(expected_active_since: float) -> int:
    remaining = expected_active_since + LONG_WORKING_SECONDS - time.time()
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
        active_since = float(state.get("active_since", 0) or 0)
        if abs(active_since - expected_active_since) > 0.001:
            return 0
        if last_mode != "working":
            return 0

        target = send_mode("attention")
        save_state("attention", target, active_since=expected_active_since)
        append_log(f"auto-attention via {target}")
    except Exception as exc:
        append_log(f"auto-attention failed: {exc}")
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
    if len(sys.argv) > 1 and sys.argv[1] == IDLE_TIMER_SENTINEL:
        try:
            return run_idle_timer(float(sys.argv[2]))
        except Exception as exc:
            append_log(f"idle timer crashed: {exc}")
            return 0

    if len(sys.argv) > 1 and sys.argv[1] == ATTENTION_TIMER_SENTINEL:
        try:
            return run_attention_timer(float(sys.argv[2]))
        except Exception as exc:
            append_log(f"attention timer crashed: {exc}")
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
        last_active_since = float(state.get("active_since", 0) or 0)

        # Let active expressions linger briefly instead of being immediately
        # overwritten by a fast follow-up idle hook.
        if mode == "idle" and last_mode in ACTIVE_MODES:
            active_age = time.time() - last_timestamp
            if active_age < MIN_ACTIVE_DISPLAY_SECONDS:
                spawn_idle_timer(last_timestamp)
                append_log(
                    f"deferred idle after {last_mode} ({active_age:.2f}s < {MIN_ACTIVE_DISPLAY_SECONDS:.2f}s)"
                )
                return 0

        if last_mode == mode and time.time() - last_timestamp < DUPLICATE_WINDOW_SECONDS:
            state_timestamp = time.time()
            active_since = last_active_since if mode in ACTIVE_MODES and last_active_since > 0 else state_timestamp
            save_state(mode, state.get("target", "duplicate"), state_timestamp, active_since=active_since)
            if mode == "working":
                spawn_attention_timer(active_since)
            append_log(f"skipped duplicate {mode}")
            return 0

        target = send_mode(mode)
        state_timestamp = time.time()
        active_since = None
        if mode in ACTIVE_MODES:
            if mode == last_mode and last_active_since > 0:
                active_since = last_active_since
            else:
                active_since = state_timestamp
        save_state(mode, target, state_timestamp, active_since=active_since)
        if mode == "working" and active_since is not None:
            spawn_attention_timer(active_since)
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
