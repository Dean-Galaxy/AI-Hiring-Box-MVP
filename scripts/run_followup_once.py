import os

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import close_browser_context, ensure_single_page, launch_browser_context
from core.followup_service import run_followup_once


def main() -> None:
    load_dotenv()
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    inbox_url = os.getenv("BOSS_INBOX_URL", "https://www.zhipin.com/web/chat/index")
    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)
        result = run_followup_once(page=page, inbox_url=inbox_url, manual=True)
        print(result)
        close_browser_context(context)


if __name__ == "__main__":
    main()
