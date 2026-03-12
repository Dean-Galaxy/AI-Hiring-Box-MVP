import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
CONTACTED_PATH = PROJECT_ROOT / "config" / "contacted_list.json"
MAIN_PID_PATH = PROJECT_ROOT / "logs" / "main.pid"


def _parse_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def require_api_auth(authorization: Optional[str] = Header(default=None)) -> None:
    configured_token = os.getenv("API_AUTH_TOKEN", "").strip()
    if not configured_token:
        # Backward-compatible by default. Set API_AUTH_TOKEN to enable auth.
        return
    incoming_token = _parse_bearer_token(authorization)
    if incoming_token != configured_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


class StartResponse(BaseModel):
    started: bool
    pid: Optional[int]
    message: str


class StopResponse(BaseModel):
    stopped: bool
    message: str


class RunStatusResponse(BaseModel):
    running: bool
    pid: Optional[int]
    started_at: Optional[float]
    uptime_seconds: int
    last_exit_code: Optional[int]
    command: str


class LeadsResponse(BaseModel):
    total: int
    items: list[Dict[str, Any]]


class MainProcessManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None
        self._last_exit_code: Optional[int] = None
        self._command = f"{sys.executable} main.py"

    def _read_pid_file(self) -> Optional[int]:
        try:
            if not MAIN_PID_PATH.exists():
                return None
            return int(MAIN_PID_PATH.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _external_running_pid(self) -> Optional[int]:
        pid = self._read_pid_file()
        if pid is None:
            return None
        if self._pid_alive(pid):
            return pid
        try:
            MAIN_PID_PATH.unlink()
        except OSError:
            pass
        return None

    def _terminate_pid(self, pid: int) -> int:
        if os.name == "nt":
            os.kill(pid, signal.SIGTERM)
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except Exception:
                os.kill(pid, signal.SIGTERM)

        for _ in range(20):
            if not self._pid_alive(pid):
                return 0
            time.sleep(0.5)

        if os.name == "nt":
            os.kill(pid, signal.SIGKILL)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except Exception:
                os.kill(pid, signal.SIGKILL)
        return 0

    def _refresh_state(self) -> None:
        if self._process is None:
            return
        rc = self._process.poll()
        if rc is None:
            return
        self._last_exit_code = rc
        self._process = None
        self._started_at = None

    def start(self) -> StartResponse:
        with self._lock:
            self._refresh_state()
            if self._process is not None:
                return StartResponse(
                    started=False,
                    pid=self._process.pid,
                    message="main.py already running",
                )
            external_pid = self._external_running_pid()
            if external_pid is not None:
                return StartResponse(
                    started=False,
                    pid=external_pid,
                    message="main.py already running",
                )

            self._process = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._started_at = time.time()
            self._last_exit_code = None
            return StartResponse(
                started=True,
                pid=self._process.pid,
                message="main.py started",
            )

    def stop(self) -> StopResponse:
        with self._lock:
            self._refresh_state()
            if self._process is None:
                external_pid = self._external_running_pid()
                if external_pid is None:
                    return StopResponse(stopped=False, message="main.py is not running")
                self._terminate_pid(external_pid)
                self._last_exit_code = 0
                self._started_at = None
                try:
                    MAIN_PID_PATH.unlink()
                except OSError:
                    pass
                return StopResponse(stopped=True, message="main.py stopped")

            process = self._process
            assert process is not None
            pid = process.pid
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(pid, signal.SIGKILL)
                process.wait(timeout=5)

            self._last_exit_code = process.returncode
            self._process = None
            self._started_at = None
            try:
                MAIN_PID_PATH.unlink()
            except OSError:
                pass
            return StopResponse(stopped=True, message="main.py stopped")

    def status(self) -> RunStatusResponse:
        with self._lock:
            self._refresh_state()
            external_pid = self._external_running_pid()
            running = self._process is not None or external_pid is not None
            pid = self._process.pid if self._process else external_pid
            started_at = self._started_at
            uptime = int(time.time() - started_at) if started_at else 0
            return RunStatusResponse(
                running=running,
                pid=pid,
                started_at=started_at,
                uptime_seconds=uptime,
                last_exit_code=self._last_exit_code,
                command=self._command,
            )


def _load_leads(status: Optional[str], limit: int) -> LeadsResponse:
    if not CONTACTED_PATH.exists():
        return LeadsResponse(total=0, items=[])

    try:
        data = json.loads(CONTACTED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return LeadsResponse(total=0, items=[])

    items = []
    for candidate_id, payload in data.items():
        row = {"candidate_id": candidate_id}
        if isinstance(payload, dict):
            row.update(payload)
        if status and row.get("status") != status:
            continue
        items.append(row)

    items.sort(key=lambda x: x.get("candidate_id", ""))
    if limit > 0:
        items = items[:limit]
    return LeadsResponse(total=len(items), items=items)


app = FastAPI(title="Auto Hiring Local API", version="1.0.0")
manager = MainProcessManager()


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    token_enabled = bool(os.getenv("API_AUTH_TOKEN", "").strip())
    return {"ok": True, "token_enabled": token_enabled}


@app.post("/run/start", response_model=StartResponse, dependencies=[Depends(require_api_auth)])
def run_start() -> StartResponse:
    return manager.start()


@app.post("/run/stop", response_model=StopResponse, dependencies=[Depends(require_api_auth)])
def run_stop() -> StopResponse:
    return manager.stop()


@app.get("/run/status", response_model=RunStatusResponse, dependencies=[Depends(require_api_auth)])
def run_status() -> RunStatusResponse:
    return manager.status()


@app.get("/leads", response_model=LeadsResponse, dependencies=[Depends(require_api_auth)])
def leads(
    status: Optional[str] = Query(default="converted"),
    limit: int = Query(default=200, ge=1, le=5000),
) -> LeadsResponse:
    return _load_leads(status=status, limit=limit)
