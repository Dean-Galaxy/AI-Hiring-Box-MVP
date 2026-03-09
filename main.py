import logging
import os
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import ensure_single_page, launch_browser_context
from core.farmer import Farmer
from core.hunter import Hunter


load_dotenv()


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
    recommend_url = os.getenv("BOSS_RECOMMEND_URL", "https://www.zhipin.com/web/geek/recommend")
    inbox_url = os.getenv("BOSS_INBOX_URL", "https://www.zhipin.com/web/geek/chat")

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)

        hunter = Hunter(page=page, recommend_url=recommend_url)
        farmer = Farmer(page=page, inbox_url=inbox_url)

        hunt_start = time.time()
        hunt_sent = 0
        while time.time() - hunt_start < 10 * 60 and hunt_sent < 20:
            hunter.navigate()
            hunter.smooth_scroll(rounds=4)
            hunt_sent += hunter.greet_candidates(max_greetings=20 - hunt_sent)
            logging.info("hunting loop current sent=%s", hunt_sent)
            time.sleep(2)

        farm_start = time.time()
        while time.time() - farm_start < 5 * 60:
            farmer.navigate_inbox()
            handled = farmer.process_unread(max_rounds=20)
            logging.info("farming loop handled=%s", handled)
            if handled == 0:
                break
            time.sleep(2)

        context.close()


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
