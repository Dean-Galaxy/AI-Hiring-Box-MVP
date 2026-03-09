import random
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Playwright


STATE_PATH = Path("config/state.json")
USER_DATA_DIR = Path("config/user_data")
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def random_sleep(min_sec: float = 0.8, max_sec: float = 2.6) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def launch_browser_context(playwright: Playwright, headless: bool = False) -> BrowserContext:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    width = random.randint(1280, 1680)
    height = random.randint(720, 980)
    kwargs = {
        "headless": headless,
        "viewport": {"width": width, "height": height},
        "user_agent": random.choice(USER_AGENTS),
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ],
    }
    if STATE_PATH.exists():
        kwargs["storage_state"] = str(STATE_PATH)

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        **kwargs,
    )

    # Mask webdriver signal to reduce bot-detection probability.
    context.add_init_script(
        """
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined
});
"""
    )
    return context


def ensure_single_page(context: BrowserContext):
    pages = context.pages
    if pages:
        return pages[0]
    return context.new_page()


def save_auth_state(context: BrowserContext, state_path: Optional[Path] = None) -> None:
    path = state_path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
