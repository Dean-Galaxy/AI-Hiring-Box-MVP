import os
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import ensure_single_page, launch_browser_context, save_auth_state


load_dotenv()


def wait_for_login_and_save() -> None:
    login_url = os.getenv("BOSS_LOGIN_URL", "https://www.zhipin.com/web/user/?ka=header-login")
    login_success_selector = ".user-nav, .header-avatar, .geek-header"

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=False)
        page = ensure_single_page(context)
        page.goto(login_url, wait_until="domcontentloaded")
        print("请在浏览器中完成二维码扫码登录...")

        deadline = time.time() + 300
        while time.time() < deadline:
            if page.locator(login_success_selector).count() > 0:
                save_auth_state(context)
                print("登录成功，已保存 state.json")
                break
            time.sleep(2)
        else:
            print("超时：5分钟内未检测到登录成功。")

        context.close()


if __name__ == "__main__":
    wait_for_login_and_save()
