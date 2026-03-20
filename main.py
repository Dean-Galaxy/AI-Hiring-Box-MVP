import atexit
import logging
import os
from datetime import datetime
from pathlib import Path
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import close_browser_context, ensure_single_page, launch_browser_context
from core.farmer import Farmer
from core.followup_service import (
    maybe_send_daily_report,
    run_followup_once,
    should_run_followup_now,
    should_send_report_now,
)
from core.hunter import Hunter
from utils.storage import load_system_state, save_system_state


load_dotenv()

PID_PATH = Path("logs/main.pid")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _today_key(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).date().isoformat()


def _get_hunt_daily_count(tz_name: str) -> int:
    today_key = _today_key(tz_name)
    state = load_system_state()
    metrics = state.get("hunt_daily_metrics", {}).get(today_key, {})
    try:
        return int(metrics.get("greeted", 0))
    except (TypeError, ValueError):
        return 0


def _add_hunt_daily_count(tz_name: str, delta: int) -> int:
    state = load_system_state()
    today_key = _today_key(tz_name)
    bucket = state.setdefault("hunt_daily_metrics", {})
    metrics = bucket.setdefault(today_key, {"greeted": 0})
    current = metrics.get("greeted", 0)
    try:
        current_count = int(current)
    except (TypeError, ValueError):
        current_count = 0
    metrics["greeted"] = current_count + max(0, int(delta))
    save_system_state(state)
    return int(metrics["greeted"])


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    handler = RotatingFileHandler(
        "logs/runner.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_pid_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")


def _cleanup_pid_file(path: Path) -> None:
    try:
        if path.exists() and path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            path.unlink()
    except OSError:
        pass


def ensure_single_instance() -> None:
    if PID_PATH.exists():
        try:
            existing_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            existing_pid = 0
        if _pid_alive(existing_pid):
            print(f"main.py already running (pid={existing_pid}), aborting duplicate start.")
            sys.exit(1)
    _write_pid_file(PID_PATH)
    atexit.register(_cleanup_pid_file, PID_PATH)

    def _handle_signal(signum, _frame) -> None:
        _cleanup_pid_file(PID_PATH)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def run_cycle() -> None:
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    recommend_url = os.getenv("BOSS_RECOMMEND_URL", "https://www.zhipin.com/web/chat/recommend")
    inbox_url = os.getenv("BOSS_INBOX_URL", "https://www.zhipin.com/web/chat/index")
    hunt_batch_size = max(1, _env_int("HUNT_BATCH_SIZE", 3))
    farm_rounds_per_batch = max(1, _env_int("FARM_ROUNDS_PER_BATCH", 8))
    hunt_window_minutes = max(1, _env_int("HUNT_WINDOW_MINUTES", 10))
    hunt_max_greetings = max(1, _env_int("HUNT_MAX_GREETINGS", 20))
    hunt_daily_limit = max(0, _env_int("HUNT_DAILY_MAX_GREETINGS", 60))
    followup_timezone = os.getenv("FOLLOWUP_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)

        hunter = Hunter(page=page, recommend_url=recommend_url)
        farmer = Farmer(page=page, inbox_url=inbox_url)

        def tick_scheduled_jobs() -> None:
            if should_run_followup_now():
                result = run_followup_once(page=page, inbox_url=inbox_url, manual=False)
                logging.info("followup scheduler result=%s", result)
            if should_send_report_now():
                result = maybe_send_daily_report()
                logging.info("followup daily report result=%s", result)

        hunt_start = time.time()
        hunt_sent = 0
        already_sent_today = _get_hunt_daily_count(followup_timezone)
        remaining_today = max(0, hunt_daily_limit - already_sent_today)
        if remaining_today <= 0:
            logging.info(
                "hunting paused: daily limit reached sent_today=%s daily_limit=%s",
                already_sent_today,
                hunt_daily_limit,
            )

        while (
            time.time() - hunt_start < hunt_window_minutes * 60
            and hunt_sent < hunt_max_greetings
            and remaining_today > 0
        ):
            tick_scheduled_jobs()
            hunter.navigate()
            hunter.smooth_scroll(rounds=4)
            current_batch_limit = min(hunt_batch_size, hunt_max_greetings - hunt_sent, remaining_today)
            greeted_now = hunter.greet_candidates(max_greetings=current_batch_limit)
            hunt_sent += greeted_now
            if greeted_now > 0:
                total_today = _add_hunt_daily_count(followup_timezone, greeted_now)
                remaining_today = max(0, hunt_daily_limit - total_today)
            else:
                remaining_today = max(0, remaining_today)
            logging.info("hunting loop batch_sent=%s total_sent=%s", greeted_now, hunt_sent)

            farmer.navigate_inbox()
            handled = farmer.process_unread(max_rounds=farm_rounds_per_batch)
            logging.info("interleaved farming handled=%s", handled)
            time.sleep(2)

        # Drain unread briefly after hunting ends.
        farm_start = time.time()
        while time.time() - farm_start < 2 * 60:
            tick_scheduled_jobs()
            farmer.navigate_inbox()
            handled = farmer.process_unread(max_rounds=20)
            logging.info("farming loop handled=%s", handled)
            if handled == 0:
                break
            time.sleep(2)

        close_browser_context(context)


def main() -> None:
    ensure_single_instance()
    setup_logging()
    while True:
        try:
            run_cycle()
        except Exception as exc:
            logging.exception("cycle failed, restarting browser: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
