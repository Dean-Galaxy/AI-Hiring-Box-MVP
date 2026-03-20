import os
import random
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright


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


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def human_type(
    page: Page,
    text: str,
    target_selector: Optional[str] = None,
    min_delay_ms: Optional[int] = None,
    max_delay_ms: Optional[int] = None,
) -> None:
    if target_selector:
        page.click(target_selector)

    env_min_delay = _env_float("TYPING_MIN_DELAY_MS", 130.0)
    env_max_delay = _env_float("TYPING_MAX_DELAY_MS", 280.0)
    low = max(40, int(min_delay_ms if min_delay_ms is not None else env_min_delay))
    high = max(low, int(max_delay_ms if max_delay_ms is not None else env_max_delay))
    pause_prob = min(max(_env_float("TYPING_PAUSE_PROB", 0.18), 0.0), 0.6)

    for idx, ch in enumerate(text):
        page.keyboard.type(ch, delay=random.randint(low, high))
        if ch in "，。！？；：,.!?;:":
            time.sleep(random.uniform(0.18, 0.45))
        elif ch in "\n":
            time.sleep(random.uniform(0.25, 0.5))
        elif idx > 0 and idx % random.randint(7, 12) == 0 and random.random() < pause_prob:
            # Occasional short "thinking" pause for more human rhythm.
            time.sleep(random.uniform(0.2, 0.75))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _attach_cdp_browser(context: BrowserContext, browser: Browser) -> BrowserContext:
    setattr(context, "_cdp_browser", browser)
    setattr(context, "_cdp_managed", True)
    return context


def _connect_cdp_context(playwright: Playwright) -> BrowserContext:
    endpoint = os.getenv("BROWSER_CDP_ENDPOINT", "http://127.0.0.1:9222").strip()
    browser = playwright.chromium.connect_over_cdp(endpoint)
    contexts = browser.contexts
    if not contexts:
        browser.close()
        raise RuntimeError("CDP 已连接但未发现可用 context，请确认手工 Chrome 已打开标签页。")
    return _attach_cdp_browser(contexts[0], browser)


def launch_browser_context(playwright: Playwright, headless: bool = False) -> BrowserContext:
    if _env_bool("BROWSER_USE_CDP", False):
        return _connect_cdp_context(playwright)

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    use_native_window = _env_bool("BROWSER_USE_NATIVE_WINDOW", True)
    locale = os.getenv("BROWSER_LOCALE", "zh-CN").strip()
    accept_language = os.getenv("BROWSER_ACCEPT_LANGUAGE", "zh-CN,zh;q=0.9,en;q=0.8").strip()
    timezone_id = os.getenv("BROWSER_TIMEZONE_ID", "Asia/Shanghai").strip()

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
    if use_native_window:
        args.append("--start-maximized")

    kwargs = {
        "headless": headless,
        "viewport": None if use_native_window else {"width": random.randint(1280, 1680), "height": random.randint(720, 980)},
        "args": args,
        "locale": locale,
        "timezone_id": timezone_id,
    }

    # Prefer stable local browser channel instead of bundled testing browser.
    browser_channel = os.getenv("BROWSER_CHANNEL", "chrome").strip()
    browser_executable_path = os.getenv("BROWSER_EXECUTABLE_PATH", "").strip()
    browser_user_agent = os.getenv("BROWSER_USER_AGENT", "").strip()

    if browser_user_agent:
        kwargs["user_agent"] = browser_user_agent

    if browser_executable_path:
        kwargs["executable_path"] = browser_executable_path
    elif browser_channel:
        kwargs["channel"] = browser_channel

    # Remove a key automation marker injected by default.
    if _env_bool("BROWSER_IGNORE_ENABLE_AUTOMATION", True):
        kwargs["ignore_default_args"] = ["--enable-automation"]

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        **kwargs,
    )

    if accept_language:
        context.set_extra_http_headers({"Accept-Language": accept_language})

    # Mask webdriver signal to reduce bot-detection probability.
    context.add_init_script(
        """
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined
});

if (!window.chrome) {
  Object.defineProperty(window, 'chrome', {
    value: { runtime: {} },
    configurable: true
  });
}

Object.defineProperty(navigator, 'languages', {
  get: () => ['zh-CN', 'zh', 'en-US', 'en'],
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


def close_browser_context(context: BrowserContext) -> None:
    # For CDP mode we only close Playwright connection, not user's Chrome process lifecycle.
    cdp_browser = getattr(context, "_cdp_browser", None)
    if cdp_browser is not None:
        cdp_browser.close()
        return
    context.close()
