import os
import time
from typing import Iterable

from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Page, sync_playwright

from core.browser_manager import close_browser_context, ensure_single_page, launch_browser_context, save_auth_state


load_dotenv()


def _looks_like_logged_in_url(url: str) -> bool:
    if "zhipin.com" not in url:
        return False
    # Login page is typically /web/user.
    if "/web/user" in url:
        return False
    return any(path in url for path in ["/web/chat", "/web/geek", "/web/job", "/web/boss"])


def _find_best_page(context: BrowserContext, fallback: Page) -> Page:
    # Prefer a zhipin page if there are multiple tabs in CDP mode.
    for p in context.pages:
        url = (p.url or "").strip()
        if "zhipin.com" in url and "about:blank" not in url:
            return p
    return fallback


def _has_login_dom(page: Page) -> bool:
    selectors: Iterable[str] = (
        ".user-nav",
        ".header-avatar",
        ".geek-header",
        "img[class*='avatar']",
        "[href*='logout']",
        "a:has-text('退出')",
        "a:has-text('我的')",
        ".chat-item",
        ".candidate-card",
    )
    return any(page.locator(selector).count() > 0 for selector in selectors)


def _has_zhipin_cookies(context: BrowserContext) -> bool:
    try:
        cookies = context.cookies()
    except Exception:
        return False
    for cookie in cookies:
        domain = cookie.get("domain", "") or ""
        value = cookie.get("value", "") or ""
        if "zhipin.com" in domain and value:
            return True
    return False


def _is_logged_in(context: BrowserContext, page: Page) -> bool:
    url_ok = _looks_like_logged_in_url(page.url or "")
    dom_ok = _has_login_dom(page)
    cookie_ok = _has_zhipin_cookies(context)
    # Any two strong signals are considered logged-in.
    return (url_ok and dom_ok) or (url_ok and cookie_ok) or (dom_ok and cookie_ok)


def wait_for_login_and_save() -> None:
    login_url = os.getenv("BOSS_LOGIN_URL", "https://www.zhipin.com/web/user/?ka=header-login")
    use_cdp = os.getenv("BROWSER_USE_CDP", "false").strip().lower() in {"1", "true", "yes", "on"}

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=False)
        page = ensure_single_page(context)
        if use_cdp:
            print("已进入 CDP 接管模式：请先在手工启动的 Chrome 中登录 Boss 并停留在主页。")
            print("脚本将检测登录状态并保存 state.json ...")
        else:
            page.goto(login_url, wait_until="domcontentloaded")
            print("请在浏览器中完成二维码扫码登录...")

        deadline = time.time() + 300
        while time.time() < deadline:
            page = _find_best_page(context, page)
            if _is_logged_in(context, page):
                save_auth_state(context)
                print("登录成功，已保存 state.json")
                break
            time.sleep(2)
        else:
            print("超时：5分钟内未检测到登录成功。")

        close_browser_context(context)


if __name__ == "__main__":
    wait_for_login_and_save()
