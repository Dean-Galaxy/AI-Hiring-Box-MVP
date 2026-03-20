import os
import platform
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_USER_DATA_DIR = PROJECT_ROOT / "config" / "manual_chrome_profile"


def _parse_endpoint(endpoint: str) -> tuple[str, int]:
    raw = (endpoint or "").strip() or DEFAULT_CDP_ENDPOINT
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "127.0.0.1").strip()
    port = int(parsed.port or 9222)
    return host, port


def _is_port_open(host: str, port: int, timeout_sec: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _resolve_chrome_executable() -> str:
    env_executable = os.getenv("BROWSER_EXECUTABLE_PATH", "").strip()
    if env_executable:
        return env_executable

    system = platform.system().lower()
    if system == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif system == "windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
            "/usr/bin/chromium-browser",
        ]

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def _launch_chrome(host: str, port: int, user_data_dir: Path) -> None:
    executable = _resolve_chrome_executable()
    if not executable:
        raise RuntimeError(
            "找不到 Chrome 可执行文件，请安装 Google Chrome 或在 .env 设置 BROWSER_EXECUTABLE_PATH。"
        )

    user_data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        executable,
        f"--remote-debugging-address={host}",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={str(user_data_dir)}",
    ]
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, **kwargs)


def _wait_ready(host: str, port: int, timeout_sec: float = 12.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.3)
    return False


def main() -> int:
    endpoint = os.getenv("BROWSER_CDP_ENDPOINT", DEFAULT_CDP_ENDPOINT).strip()
    host, port = _parse_endpoint(endpoint)
    user_data_dir = Path(os.getenv("BROWSER_CDP_USER_DATA_DIR", "").strip() or DEFAULT_USER_DATA_DIR)
    if not user_data_dir.is_absolute():
        user_data_dir = (PROJECT_ROOT / user_data_dir).resolve()

    if _is_port_open(host, port):
        print(f"ready cdp={host}:{port} browser=already_running")
        return 0

    try:
        _launch_chrome(host=host, port=port, user_data_dir=user_data_dir)
    except Exception as exc:
        print(f"error prepare_failed reason={exc}")
        return 1

    if _wait_ready(host, port, timeout_sec=12.0):
        print(f"ready cdp={host}:{port} profile={user_data_dir}")
        return 0

    print("error cdp_not_ready 请检查 Chrome 是否被系统拦截或路径配置是否正确")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
