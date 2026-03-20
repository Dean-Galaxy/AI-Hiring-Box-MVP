import os

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from core.browser_manager import ensure_single_page, launch_browser_context, close_browser_context
from core.hunter import Hunter


def main() -> None:
    """
    极简测试：在推荐页上针对当前可见的第一张“继续沟通/已沟通/沟通”卡片，
    尝试用 Hunter._open_chat_after_greet 打开聊天窗口。

    使用方法：
    1. 先手动启动 Chrome 并登录 Boss 直聘；
    2. 打开推荐页：https://www.zhipin.com/web/chat/recommend
       滚动到有“继续沟通”或“已沟通/沟通”按钮的卡片区域；
    3. 在项目根目录执行：
         python -m scripts.test_hunter_open_chat_once
    4. 观察：
       - 页面是否弹出聊天窗口；
       - 弹窗标题是否与该卡片上的候选人姓名一致；
       - 终端输出：
         "[TEST] _open_chat_after_greet opened_chat=..."；
       - logs/runner.log（如果 main.py 也在跑）中是否减少
         "hunter failed to open chat after greet" / TargetClosedError。
    """

    load_dotenv()
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    recommend_url = os.getenv("BOSS_RECOMMEND_URL", "https://www.zhipin.com/web/chat/recommend")

    with sync_playwright() as p:
        context = launch_browser_context(p, headless=headless)
        page = ensure_single_page(context)
        page.goto(recommend_url, wait_until="domcontentloaded")

        hunter = Hunter(page=page, recommend_url=recommend_url)

        # 直接在当前 frame/page 上拿第一张含“继续沟通/已沟通/沟通”按钮的卡片做实验。
        scope = hunter._find_recommend_frame() or page
        cards = scope.locator(
            ".candidate-card, .geek-card, .card-item, .candidate-item, "
            "[class*='candidate'][class*='card'], [class*='geek'][class*='card']"
        )
        total = cards.count()
        print(f"[TEST] visible cards={total}")

        target_card = None
        candidate_name = ""
        for i in range(total):
            card = cards.nth(i)
            btn = card.locator(
                "button:has-text('继续沟通'), a:has-text('继续沟通'), "
                "button:has-text('已沟通'), a:has-text('已沟通'), "
                "button:has-text('沟通'), a:has-text('沟通')"
            )
            if btn.count() == 0:
                continue
            target_card = card
            name_locator = card.locator(".name, [class*='name']").first
            candidate_name = (name_locator.inner_text().strip() if name_locator.count() else "")
            break

        if target_card is None:
            print("[TEST] 未找到包含“继续沟通/已沟通/沟通”按钮的卡片，请在推荐页手动滚动到相应区域后重试。")
        else:
            opened = hunter._open_chat_after_greet(target_card, candidate_name=candidate_name, allow_global_fallback=False)
            print(f"[TEST] _open_chat_after_greet opened_chat={opened} candidate_name={candidate_name!r}")

        close_browser_context(context)


if __name__ == "__main__":
    main()

