import re
import logging
import os
from typing import Dict, Optional

from playwright.sync_api import Error, Frame, Page, TimeoutError as PlaywrightTimeoutError

from core.browser_manager import random_sleep
from utils.storage import load_contacted_map, upsert_candidate_status


class Hunter:
    def __init__(self, page: Page, recommend_url: str):
        self.page = page
        self.recommend_url = recommend_url
        self.proactive_enabled = os.getenv("PROACTIVE_FIRST_MESSAGE_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.proactive_template = os.getenv("PROACTIVE_FIRST_MESSAGE_TEMPLATE", "").strip()

    def navigate(self) -> None:
        self._pick_working_page()
        current_url = (self.page.url or "").strip()
        logging.info("hunter current_url=%s", current_url)
        # Avoid full-page reload when already on recommend page.
        if "/web/chat/recommend" not in current_url and "/web/geek/recommend" not in current_url:
            self.page.goto(self.recommend_url, wait_until="domcontentloaded")
            current_url = (self.page.url or "").strip()
            logging.info("hunter navigated_url=%s", current_url)
        # Some accounts cannot access /web/geek/* and must use /web/chat/*.
        if self.page.locator("text=请切换身份后再试").count() > 0 and "/web/chat/recommend" not in self.page.url:
            self.page.goto("https://www.zhipin.com/web/chat/recommend", wait_until="domcontentloaded")
        frame = self._find_recommend_frame()
        if frame is not None:
            logging.info("hunter recommend frame=%s", frame.url)
        random_sleep(1.2, 2.8)

    def _pick_working_page(self) -> None:
        pages = self.page.context.pages
        if not pages:
            return
        for p in reversed(pages):
            url = (p.url or "").strip()
            if "/web/chat/recommend" in url:
                self.page = p
                return
        for p in reversed(pages):
            url = (p.url or "").strip()
            if "zhipin.com/web/chat" in url:
                self.page = p
                return
        for p in reversed(pages):
            url = (p.url or "").strip()
            if "zhipin.com" in url and "about:blank" not in url:
                self.page = p
                return

    def _find_recommend_frame(self) -> Optional[Frame]:
        for frame in self.page.frames:
            url = (frame.url or "").strip()
            if "/web/frame/recommend" in url:
                return frame
        return None

    def _dismiss_blocking_dialog(self) -> None:
        # Candidate detail dialog can block pointer events over recommend cards.
        close_selectors = [
            ".dialog-wrap.active .close",
            ".dialog-wrap.active .icon-close",
            ".dialog-wrap.active [class*='close']",
            ".dialog-wrap.active button:has-text('关闭')",
            ".dialog-wrap.active .btn-close",
        ]
        for selector in close_selectors:
            close_btn = self.page.locator(selector).first
            if close_btn.count() == 0:
                continue
            try:
                close_btn.click(timeout=800)
                random_sleep(0.2, 0.4)
                return
            except Error:
                continue

    def _send_proactive_first_message(self) -> bool:
        if not self.proactive_enabled or not self.proactive_template:
            return False
        textarea_selector = "textarea.chat-input"
        editable_selector = "div[contenteditable='true']"
        if self.page.locator(f"{textarea_selector}, {editable_selector}").count() == 0:
            return False
        try:
            if self.page.locator(textarea_selector).count() > 0:
                self.page.click(textarea_selector)
                self.page.type(textarea_selector, self.proactive_template, delay=80)
            else:
                target = self.page.locator(editable_selector).first
                target.click()
                self.page.keyboard.type(self.proactive_template, delay=80)
            random_sleep(0.3, 0.8)
            send_btn = self.page.locator("button:has-text('发送')")
            if send_btn.count() > 0:
                send_btn.first.click(timeout=1200)
            else:
                self.page.keyboard.press("Enter")
            return True
        except Error:
            return False

    def smooth_scroll(self, rounds: int = 5) -> None:
        frame = self._find_recommend_frame()
        for _ in range(rounds):
            if frame is not None:
                for _ in range(4):
                    try:
                        frame.evaluate("window.scrollBy(0, 300)")
                    except Error:
                        break
                    random_sleep(0.2, 0.5)
                random_sleep(0.8, 1.8)
                continue
            distance = 300
            for _ in range(4):
                self.page.mouse.wheel(0, distance)
                random_sleep(0.2, 0.5)
            random_sleep(0.8, 1.8)

    def _parse_age(self, raw_text: str) -> Optional[int]:
        match = re.search(r"(\d{2})岁", raw_text)
        return int(match.group(1)) if match else None

    def _candidate_from_card(self, card) -> Dict[str, str]:
        name_locator = card.locator(".name, [class*='name']").first
        active_locator = card.locator(".active-time, [class*='active']").first
        expect_locator = card.locator(".expect-position, [class*='expect'], [class*='position'], [class*='job']").first
        base_info_locator = card.locator(".base-info, [class*='base'], [class*='info']").first
        profile_url = card.get_attribute("href") or ""
        link_locator = card.locator("a[href*='zhipin.com']").first
        if not profile_url and link_locator.count():
            profile_url = link_locator.get_attribute("href") or ""
        return {
            "candidate_id": card.get_attribute("data-geek-id") or card.get_attribute("data-id") or "",
            "name": (name_locator.inner_text(timeout=1000).strip() if name_locator.count() else ""),
            "active_status": (active_locator.inner_text(timeout=1000).strip() if active_locator.count() else ""),
            "expected_job": (expect_locator.inner_text(timeout=1000).strip() if expect_locator.count() else ""),
            "age_text": (base_info_locator.inner_text(timeout=1000).strip() if base_info_locator.count() else card.inner_text(timeout=1000).strip()),
            "profile_url": profile_url,
        }

    def _match_filter(self, candidate: Dict[str, str]) -> bool:
        # If page structure changed and parsing is partial, avoid over-filtering.
        if not candidate["expected_job"] and not candidate["active_status"]:
            return True

        age = self._parse_age(candidate["age_text"])
        if age is not None and (age < 18 or age > 50):
            return False

        if candidate["active_status"]:
            active_ok = any(flag in candidate["active_status"] for flag in ["刚刚活跃", "今日活跃", "在线", "活跃"])
            if not active_ok:
                return False

        if not candidate["expected_job"]:
            return True

        job_ok = any(k in candidate["expected_job"] for k in ["外卖", "骑手", "配送", "送餐", "快递"])
        if not job_ok:
            return False
        return True

    def greet_candidates(self, max_greetings: int = 20) -> int:
        greeted = 0
        contacted = load_contacted_map()
        scope = self._find_recommend_frame() or self.page
        cards = scope.locator(
            ".candidate-card, .geek-card, .card-item, .candidate-item, [class*='candidate'][class*='card'], [class*='geek'][class*='card'], [class*='card']:has(button:has-text('打招呼')), [class*='card']:has(a:has-text('打招呼'))"
        )
        total = cards.count()
        logging.info("hunter scan cards=%s max_greetings=%s", total, max_greetings)

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

            greet_btn = card.locator(
                "button:has-text('打招呼'), button:has-text('沟通'), a:has-text('打招呼'), a:has-text('沟通'), [role='button']:has-text('打招呼'), [role='button']:has-text('沟通')"
            )
            if greet_btn.count() == 0:
                continue

            self._dismiss_blocking_dialog()
            try:
                greet_btn.first.click(timeout=2000)
                random_sleep(0.8, 1.6)
            except PlaywrightTimeoutError:
                # Dialog/iframe overlay may intercept click; skip this card instead of failing the whole cycle.
                self._dismiss_blocking_dialog()
                continue
            except Error:
                continue

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
            else:
                # On some layouts status text updates outside card; treat successful click as greeted.
                greeted += 1

            if self._send_proactive_first_message():
                logging.info("hunter proactive message sent candidate_id=%s", candidate_id)

        # Fallback for pages that do not expose stable card classes.
        if greeted == 0 and max_greetings > 0:
            global_btns = scope.locator(
                "button:has-text('打招呼'), a:has-text('打招呼'), [role='button']:has-text('打招呼')"
            )
            fallback_total = global_btns.count()
            logging.info("hunter fallback buttons=%s", fallback_total)
            for i in range(fallback_total):
                if greeted >= max_greetings:
                    break
                btn = global_btns.nth(i)
                try:
                    self._dismiss_blocking_dialog()
                    btn.click(timeout=2000)
                    random_sleep(0.8, 1.6)
                    greeted += 1
                except Error:
                    continue

        logging.info("hunter round greeted=%s", greeted)
        return greeted
