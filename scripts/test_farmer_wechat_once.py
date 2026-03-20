import os

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import ensure_single_page, launch_browser_context, close_browser_context
from core.farmer import Farmer


def main() -> None:
    """
    极简测试：在当前已打开的对话窗口里，尝试点击“同意交换微信”。

    使用方法：
    1. 先手动启动 Chrome 并登录 Boss 直聘；
    2. 打开含有“交换微信绿卡片”的会话窗口（右侧能看到那张卡片）；
    3. 在项目根目录执行：
         python -m scripts.test_farmer_wechat_once
    4. 观察：
       - 页面上的“同意”是否被自动点击；
       - logs/runner.log 中是否出现
         "farmer clicked wechat agree via green card" 或 "via blue notice"。
    """

    load_dotenv()
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)

        # 此时假定你已经手动在该 page 上打开了目标会话
        farmer = Farmer(page=page, inbox_url=page.url)
        clicked = farmer._accept_exchange_wechat()
        print(f"[TEST] _accept_exchange_wechat clicked={clicked}")

        close_browser_context(context)


if __name__ == "__main__":
    main()

