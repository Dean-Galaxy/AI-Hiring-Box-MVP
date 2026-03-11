import logging
import os
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import close_browser_context, ensure_single_page, launch_browser_context
from core.farmer import Farmer
from core.hunter import Hunter


load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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


def run_cycle() -> None:
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    recommend_url = os.getenv("BOSS_RECOMMEND_URL", "https://www.zhipin.com/web/chat/recommend")
    inbox_url = os.getenv("BOSS_INBOX_URL", "https://www.zhipin.com/web/chat/index")
    hunt_batch_size = max(1, _env_int("HUNT_BATCH_SIZE", 3))
    farm_rounds_per_batch = max(1, _env_int("FARM_ROUNDS_PER_BATCH", 8))
    hunt_window_minutes = max(1, _env_int("HUNT_WINDOW_MINUTES", 10))
    hunt_max_greetings = max(1, _env_int("HUNT_MAX_GREETINGS", 20))

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)

        hunter = Hunter(page=page, recommend_url=recommend_url)
        farmer = Farmer(page=page, inbox_url=inbox_url)

        hunt_start = time.time()
        hunt_sent = 0
        while time.time() - hunt_start < hunt_window_minutes * 60 and hunt_sent < hunt_max_greetings:
            hunter.navigate()
            hunter.smooth_scroll(rounds=4)
            current_batch_limit = min(hunt_batch_size, hunt_max_greetings - hunt_sent)
            greeted_now = hunter.greet_candidates(max_greetings=current_batch_limit)
            hunt_sent += greeted_now
            logging.info("hunting loop batch_sent=%s total_sent=%s", greeted_now, hunt_sent)

            farmer.navigate_inbox()
            handled = farmer.process_unread(max_rounds=farm_rounds_per_batch)
            logging.info("interleaved farming handled=%s", handled)
            time.sleep(2)

        # Drain unread briefly after hunting ends.
        farm_start = time.time()
        while time.time() - farm_start < 2 * 60:
            farmer.navigate_inbox()
            handled = farmer.process_unread(max_rounds=20)
            logging.info("farming loop handled=%s", handled)
            if handled == 0:
                break
            time.sleep(2)

        close_browser_context(context)


def main() -> None:
    setup_logging()
    while True:
        try:
            run_cycle()
        except Exception as exc:
            logging.exception("cycle failed, restarting browser: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
