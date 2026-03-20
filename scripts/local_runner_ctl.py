import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PID_PATH = PROJECT_ROOT / "logs" / "main.pid"
MAIN_PATH = PROJECT_ROOT / "main.py"
STDOUT_LOG_PATH = PROJECT_ROOT / "logs" / "main.stdout.log"
STDERR_LOG_PATH = PROJECT_ROOT / "logs" / "main.stderr.log"


COMMAND_ALIASES = {
    "start": "start",
    "run": "start",
    "begin": "start",
    "启动": "start",
    "开始": "start",
    "开始招聘": "start",
    "启动招聘": "start",
    "开始招人": "start",
    "status": "status",
    "state": "status",
    "状态": "status",
    "查看状态": "status",
    "招聘状态": "status",
    "运行状态": "status",
    "stop": "stop",
    "end": "stop",
    "停止": "stop",
    "结束": "stop",
    "停止招聘": "stop",
    "结束招聘": "stop",
    "暂停招聘": "stop",
}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid() -> int:
    if not PID_PATH.exists():
        return 0
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _wait_for_pid_file(timeout_sec: float = 8.0) -> int:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        pid = _read_pid()
        if pid and _pid_alive(pid):
            return pid
        time.sleep(0.2)
    return 0


def cmd_start() -> int:
    running_pid = _read_pid()
    if running_pid and _pid_alive(running_pid):
        print(f"already_running pid={running_pid}")
        return 0

    if not MAIN_PATH.exists():
        print(f"error main.py_not_found path={MAIN_PATH}")
        return 1

    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)

    stdout_f = STDOUT_LOG_PATH.open("a", encoding="utf-8")
    stderr_f = STDERR_LOG_PATH.open("a", encoding="utf-8")
    popen_kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdout": stdout_f,
        "stderr": stderr_f,
        "start_new_session": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen([sys.executable, str(MAIN_PATH)], **popen_kwargs)
    except Exception as exc:  # pragma: no cover
        print(f"error start_failed reason={exc}")
        return 1
    finally:
        stdout_f.close()
        stderr_f.close()

    pid = _wait_for_pid_file(timeout_sec=10.0)
    if pid:
        print(f"started pid={pid}")
        return 0

    print("error start_timeout_pid_not_ready")
    return 1


def cmd_status() -> int:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"running pid={pid}")
        return 0

    if pid and not _pid_alive(pid):
        try:
            PID_PATH.unlink()
        except OSError:
            pass
    print("stopped")
    return 0


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        os.kill(pid, signal.SIGTERM)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            os.kill(pid, signal.SIGTERM)


def cmd_stop() -> int:
    pid = _read_pid()
    if not pid:
        print("stopped already")
        return 0
    if not _pid_alive(pid):
        try:
            PID_PATH.unlink()
        except OSError:
            pass
        print("stopped already")
        return 0

    try:
        _terminate_pid(pid)
    except OSError as exc:
        print(f"error stop_failed reason={exc}")
        return 1

    deadline = time.time() + 12
    while time.time() < deadline:
        if not _pid_alive(pid):
            try:
                PID_PATH.unlink()
            except OSError:
                pass
            print(f"stopped pid={pid}")
            return 0
        time.sleep(0.3)

    # Escalate to SIGKILL only if process does not exit.
    try:
        if os.name == "nt":
            os.kill(pid, signal.SIGKILL)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    try:
        PID_PATH.unlink()
    except OSError:
        pass
    print(f"stopped_force pid={pid}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local process controller for main.py (no API required).",
    )
    parser.add_argument(
        "command",
        help="Command or Chinese alias, e.g. start/status/stop or 开始招聘/查看状态/停止招聘",
    )
    return parser


def _normalize_command(raw_command: str) -> str:
    return COMMAND_ALIASES.get((raw_command or "").strip().lower(), "")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = _normalize_command(args.command)
    if command == "start":
        return cmd_start()
    if command == "stop":
        return cmd_stop()
    if command == "status":
        return cmd_status()

    accepted = "start/status/stop 或 开始招聘/查看状态/停止招聘"
    print(f"error unsupported_command command={args.command} accepted={accepted}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
