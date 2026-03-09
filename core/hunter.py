import re
from typing import Dict, List, Optional

from playwright.sync_api import Error, Page

from core.browser_manager import random_sleep
from utils.storage import load_contacted_map, upsert_candidate_status


class Hunter:
    def __init__(self, page: Page, recommend_url: str):
        self.page = page
        self.recommend_url = recommend_url

    def navigate(self) -> None:
        self.page.goto(self.recommend_url, wait_until="domcontentloaded")
        random_sleep(1.2, 2.8)

    def smooth_scroll(self, rounds: int = 5) -> None:
        for _ in range(rounds):
            distance = 300
            for _ in range(4):
                self.page.mouse.wheel(0, distance)
                random_sleep(0.2, 0.5)
            random_sleep(0.8, 1.8)

    def _parse_age(self, raw_text: str) -> Optional[int]:
        match = re.search(r"(\d{2})岁", raw_text)
        return int(match.group(1)) if match else None

    def _candidate_from_card(self, card) -> Dict[str, str]:
        return {
            "candidate_id": card.get_attribute("data-geek-id") or "",
            "name": (card.locator(".name").first.inner_text(timeout=1000).strip() if card.locator(".name").count() else ""),
            "active_status": (card.locator(".active-time").first.inner_text(timeout=1000).strip() if card.locator(".active-time").count() else ""),
            "expected_job": (card.locator(".expect-position").first.inner_text(timeout=1000).strip() if card.locator(".expect-position").count() else ""),
            "age_text": (card.locator(".base-info").first.inner_text(timeout=1000).strip() if card.locator(".base-info").count() else ""),
            "profile_url": card.get_attribute("href") or "",
        }

    def _match_filter(self, candidate: Dict[str, str]) -> bool:
        age = self._parse_age(candidate["age_text"])
        if age is None or age < 18 or age > 45:
            return False

        active_ok = any(flag in candidate["active_status"] for flag in ["刚刚活跃", "今日活跃", "在线"])
        if not active_ok:
            return False

        job_ok = any(k in candidate["expected_job"] for k in ["外卖", "骑手", "配送"])
        return job_ok

    def greet_candidates(self, max_greetings: int = 20) -> int:
        greeted = 0
        contacted = load_contacted_map()
        cards = self.page.locator(".candidate-card")
        total = cards.count()

        for idx in range(total):
            if greeted >= max_greetings:
                break

            card = cards.nth(idx)
            try:
                candidate = self._candidate_from_card(card)
            except Error:
                continue

            candidate_id = candidate["candidate_id"] or candidate["profile_url"] or f"card-{idx}"
            if candidate_id in contacted:
                continue

            if not self._match_filter(candidate):
                continue

            greet_btn = card.locator("button:has-text('打招呼'), button:has-text('沟通')")
            if greet_btn.count() == 0:
                continue

            greet_btn.first.click(timeout=1500)
            random_sleep(0.8, 1.6)

            status_text = card.inner_text().strip()
            sent = "已沟通" in status_text or "继续沟通" in status_text or "已发送" in status_text
            if sent:
                upsert_candidate_status(
                    candidate_id,
                    {
                        "name": candidate["name"],
                        "profile_url": candidate["profile_url"],
                        "status": "contacted",
                    },
                )
                greeted += 1

        return greeted
