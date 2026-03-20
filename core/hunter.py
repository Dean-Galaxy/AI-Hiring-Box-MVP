import re
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import Error, Frame, Page, TimeoutError as PlaywrightTimeoutError

from core.browser_manager import human_type, random_sleep
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

    def _chat_popup(self):
        return self.page.locator(".chat-global-conversation").first

    def _is_chat_popup_open(self) -> bool:
        popup = self._chat_popup()
        if popup.count() == 0:
            return False
        try:
            return popup.is_visible()
        except Error:
            return False

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
        if not self._is_chat_popup_open():
            return False
        textarea_selector = "textarea.chat-input"
        editable_selector = (
            ".chat-global-conversation #boss-chat-global-input, "
            ".chat-global-conversation div.bosschat-chat-input[contenteditable='true'], "
            ".chat-global-conversation div[contenteditable='true']"
        )
        if self.page.locator(f"{textarea_selector}, {editable_selector}").count() == 0:
            return False
        try:
            if self.page.locator(textarea_selector).count() > 0:
                human_type(self.page, self.proactive_template, target_selector=textarea_selector)
            else:
                target = self.page.locator(editable_selector).first
                target.click()
                # For Boss global popup editor, always type into the exact input.
                if self.page.locator(".chat-global-conversation #boss-chat-global-input").count() > 0:
                    human_type(
                        self.page,
                        self.proactive_template,
                        target_selector=".chat-global-conversation #boss-chat-global-input",
                    )
                else:
                    human_type(self.page, self.proactive_template)
            random_sleep(0.3, 0.8)
            send_btn = self.page.locator(
                ".chat-global-conversation .chat-op .btn-send:not(.btn-disabled), "
                ".chat-global-conversation .btn-send:not(.btn-disabled), "
                ".chat-global-conversation button:has-text('发送')"
            )
            if send_btn.count() > 0 and send_btn.first.is_visible():
                send_btn.first.click(timeout=1200)
            else:
                self.page.keyboard.press("Enter")
            return True
        except Error:
            return False

    def _has_template_sent_in_chat(self) -> bool:
        if not self.proactive_template:
            return False
        my_bubbles = self.page.locator(".chat-global-conversation .item-myself")
        if my_bubbles.count() == 0:
            my_bubbles = self.page.locator(".chat-global-conversation .message-item.me")
        total = my_bubbles.count()
        start = max(0, total - 8)
        for i in range(start, total):
            try:
                text = my_bubbles.nth(i).inner_text().strip()
            except Error:
                continue
            if self.proactive_template in text:
                return True
        return False

    def _has_candidate_reply_in_chat(self) -> bool:
        # Strictly trust real candidate bubbles only.
        candidate_bubbles = self.page.locator(".chat-global-conversation .item-friend")
        if candidate_bubbles.count() == 0:
            return False
        total = candidate_bubbles.count()
        start = max(0, total - 10)
        for i in range(start, total):
            bubble = candidate_bubbles.nth(i)
            try:
                text = bubble.inner_text().strip()
                css = (bubble.get_attribute("class") or "").lower()
            except Error:
                continue
            if not text:
                continue
            # Ignore system cards/timestamps in popup chat.
            if "item-system" in css:
                continue
            if any(flag in css for flag in ["system", "tip", "time", "status", "phone", "call", "position"]):
                continue
            if any(flag in text for flag in ["沟通的职位", "去打电话", "该牛人已开启虚拟电话"]):
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", text):
                continue
            if len(text) < 2:
                continue
            return True
        return False

    def _has_chat_input(self) -> bool:
        if not self._is_chat_popup_open():
            return False
        return self.page.locator(
            ".chat-global-conversation textarea.chat-input, "
            ".chat-global-conversation #boss-chat-global-input, "
            ".chat-global-conversation div.bosschat-chat-input[contenteditable='true'], "
            ".chat-global-conversation div[contenteditable='true']"
        ).count() > 0

    def _chat_title_text(self) -> str:
        title = self.page.locator(
            ".chat-global-conversation .chatview-name, "
            ".chat-global-conversation .name, "
            ".dialog-con .name, .dialog-con [class*='name'], .chat-dialog .name, .chat-container .name, .geek-name"
        ).first
        if title.count() == 0:
            return ""
        try:
            return title.inner_text().strip()
        except Error:
            return ""

    def _panel_matches_candidate(self, candidate_name: str) -> bool:
        name = (candidate_name or "").strip()
        if not name:
            return True
        title = self._chat_title_text()
        if not title:
            return True
        clean_name = re.sub(r"\s+", "", name)
        clean_title = re.sub(r"\s+", "", title)
        return clean_name in clean_title or clean_title in clean_name

    def _open_chat_after_greet(self, card, candidate_name: str = "", allow_global_fallback: bool = False) -> bool:
        """
        严格在当前 card 作用域内操作，并使用绝对文本匹配，杜绝误触全局导航栏。
        """
        # 兼容旧调用参数，但此函数不再做全局继续沟通 fallback。
        _ = allow_global_fallback

        # 聊天弹窗已经打开且标题匹配，直接视为成功。
        if self._has_chat_input() and self._panel_matches_candidate(candidate_name):
            return True

        # 1. 严格使用 :text-is() 绝对匹配，并兼容 button / a 标签。
        greet_btn = card.locator('button:text-is("打招呼"), a:text-is("打招呼")').first
        continue_btn = card.locator(
            'button:text-is("继续沟通"), a:text-is("继续沟通"), button:text-is("已沟通"), a:text-is("已沟通")'
        ).first

        # 2. 尝试打招呼（只在当前 card 内）。
        try:
            if greet_btn.is_visible():
                greet_btn.click(timeout=2000)
                logging.info("hunter 已点击 %s 的打招呼", candidate_name or "候选人")
                try:
                    continue_btn.wait_for(state="visible", timeout=3000)
                except PlaywrightTimeoutError:
                    logging.warning(
                        "hunter %s 打招呼后，未能在当前卡片内刷出继续沟通按钮",
                        candidate_name or "候选人",
                    )
                    return False
        except Error:
            return False

        # 3. 点击继续沟通（只在当前 card 内）并校验聊天窗口。
        try:
            if continue_btn.is_visible():
                self.page.wait_for_timeout(500)
                continue_btn.click(timeout=2000)
                try:
                    self.page.wait_for_selector(
                        ".chat-message-list, .chat-modal-container, .chat-global-conversation",
                        timeout=5000,
                    )

                    # 二次校验名字，彻底杜绝串人。
                    chat_title = self.page.locator(
                        ".chat-modal-header .name, .chatview-name, .name-wrap .name, "
                        ".chat-global-conversation .chatview-name, .chat-global-conversation .name"
                    ).first
                    title_text = ""
                    if chat_title.count() > 0:
                        title_text = chat_title.inner_text().strip()
                    if candidate_name and title_text and candidate_name not in title_text:
                        logging.error(
                            "hunter 弹窗名字不匹配，预期: %s, 实际: %s",
                            candidate_name,
                            title_text,
                        )
                        close_btn = self.page.locator(
                            ".icon-close, .close-btn, .chat-global-top .iboss-close, .dialog-con .icon-close"
                        ).first
                        if close_btn.count() > 0 and close_btn.is_visible():
                            close_btn.click(timeout=1200)
                        return False
                    return True
                except PlaywrightTimeoutError as exc:
                    logging.error("hunter 等待聊天框超时或被关闭: %s", exc)
                    return False
        except Error:
            return False
        return False

    def _latest_my_message(self) -> str:
        my_bubbles = self.page.locator(".message-item.me")
        if my_bubbles.count() == 0:
            return ""
        try:
            return my_bubbles.last.inner_text().strip()
        except Error:
            return ""

    def _close_chat_panel(self) -> bool:
        close_selectors = [
            ".chat-global-top .iboss-close",
            ".conversation-bd-content .iboss-close",
            ".chat-global-conversation .iboss-close",
            ".dialog-con .op-close",
            ".dialog-con .icon-close",
            ".chat-dialog .close",
            ".chat-container .close",
            ".boss-dialog .icon-close",
            ".boss-popup .icon-close",
            ".boss-popup [class*='close']",
            "button[aria-label='关闭']",
            "button:has-text('关闭')",
            "[class*='close']:visible",
        ]
        for selector in close_selectors:
            btn = self.page.locator(selector).first
            if btn.count() == 0:
                continue
            try:
                btn.click(timeout=1200)
                random_sleep(0.2, 0.5)
                return True
            except Error:
                continue
        return False

    def _send_proactive_once_then_close(self, candidate_id: str = "") -> bool:
        if not self.proactive_enabled or not self.proactive_template:
            # Even when proactive is disabled, close popup to avoid blocking recommend flow.
            return self._close_chat_panel()
        if not self._has_chat_input():
            return False

        # Do not repeat first greeting when it already exists in chat.
        if self._has_template_sent_in_chat():
            closed = self._close_chat_panel()
            if not closed:
                logging.warning("hunter close chat panel failed after existing proactive message candidate_id=%s", candidate_id)
            return True

        # Candidate already replied: skip first greeting and hand over to farming stage.
        if self._has_candidate_reply_in_chat():
            closed = self._close_chat_panel()
            if not closed:
                logging.warning("hunter close chat panel failed after candidate replied candidate_id=%s", candidate_id)
            logging.info("hunter proactive skipped because candidate already replied candidate_id=%s", candidate_id)
            return True

        sent = self._send_proactive_first_message()
        if not sent:
            return False

        random_sleep(0.4, 0.9)
        closed = self._close_chat_panel()
        if not closed:
            logging.warning("hunter close chat panel failed candidate_id=%s", candidate_id)
        return True

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

    def _extract_city(self, candidate: Dict[str, str]) -> str:
        pool = " ".join(
            [
                candidate.get("expected_job", ""),
                candidate.get("age_text", ""),
                candidate.get("active_status", ""),
            ]
        )
        match = re.search(r"([\u4e00-\u9fa5]{2,}(?:市|区|县))", pool)
        if match:
            return match.group(1)
        for token in re.split(r"[\s/|,，]+", pool):
            token = token.strip()
            if 1 < len(token) <= 8 and re.fullmatch(r"[\u4e00-\u9fa5]+", token):
                return token
        return ""

    def _extract_expected_job(self, candidate: Dict[str, str]) -> str:
        raw = candidate.get("expected_job", "")
        if not raw:
            return ""
        for token in re.split(r"[\s/|,，]+", raw):
            token = token.strip()
            if any(k in token for k in ["骑手", "配送", "送餐", "外卖", "快递"]):
                return token
        return raw.strip()

    def _build_followup_key(self, candidate: Dict[str, str]) -> str:
        tz_name = os.getenv("FOLLOWUP_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
        greet_date = datetime.now(ZoneInfo(tz_name)).date().isoformat()
        age_value = self._parse_age(candidate.get("age_text", "") or "")
        fields = [
            (candidate.get("name", "") or "").strip(),
            greet_date,
            str(age_value or ""),
            self._extract_city(candidate),
            self._extract_expected_job(candidate),
        ]
        return "|".join(fields)

    def _is_high_intent_card(self, card) -> bool:
        try:
            text = card.inner_text().strip()
            keywords = ["意愿强", "想当骑手", "有骑手经验", "做过骑手", "跑过外卖"]
            return any(k in text for k in keywords)
        except Error:
            return False

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
        open_chat_attempted = 0
        open_chat_success = 0
        contacted = load_contacted_map()
        scope = self._find_recommend_frame() or self.page
        logging.info("hunter pre-scrolling to load more candidates for priority filtering...")
        self.smooth_scroll(rounds=3)
        # 重新获取加载后的节点
        cards = scope.locator(
            ".candidate-card, .geek-card, .card-item, .candidate-item, .geek-item, .geek-item-wrap"
        )
        total = cards.count()
        logging.info("hunter scan cards=%s max_greetings=%s", total, max_greetings)

        for pass_num in [1, 2]:
            if greeted >= max_greetings:
                break
            logging.info("hunter sequential pass=%s total_cards=%s", pass_num, total)
            for idx in range(total):
                if greeted >= max_greetings:
                    break

                card = cards.nth(idx)
                # 【核心修复】：前置获取按钮并校验。只有恰好包含 1 个“打招呼”按钮的节点，才是真正的单人独立卡片，彻底过滤掉把两人包在一起的“整行父容器”。
                greet_btn = card.locator(
                    "button:has-text('打招呼'), a:has-text('打招呼'), [role='button']:has-text('打招呼')"
                )
                if greet_btn.count() != 1:
                    continue

                # 此时 card 绝对属于一个具体的人，再进行意向判断
                is_high_intent = self._is_high_intent_card(card)
                if pass_num == 1 and not is_high_intent:
                    continue
                if pass_num == 2 and is_high_intent:
                    continue

                try:
                    candidate = self._candidate_from_card(card)
                except Error:
                    continue

                candidate_id = candidate["candidate_id"] or candidate["profile_url"] or f"card-{idx}"
                if candidate_id in contacted:
                    continue

                if not self._match_filter(candidate):
                    continue

                # 一人一闭环：点击前先确保屏幕干净
                self._close_chat_panel()
                self._dismiss_blocking_dialog()

                # 直接交给内层函数去执行 [打招呼 -> 等待 -> 继续沟通] 的全套原子动作
                opened_chat = self._open_chat_after_greet(card, candidate_name=candidate.get("name", ""))
                open_chat_attempted += 1

                if not opened_chat:
                    logging.warning("hunter failed to open chat after greet candidate_id=%s", candidate_id)
                    self._close_chat_panel()
                else:
                    open_chat_success += 1
                    greeted += 1
                    # 只有成功打开了会话窗口，才算作有效触达并写入本地存储
                    tz_name = os.getenv("FOLLOWUP_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
                    now_local = datetime.now(ZoneInfo(tz_name))
                    age_value = self._parse_age(candidate.get("age_text", "") or "")
                    upsert_candidate_status(
                        candidate_id,
                        {
                            "name": candidate["name"],
                            "profile_url": candidate["profile_url"],
                            "status": "contacted",
                            "first_greet_at": now_local.isoformat(timespec="seconds"),
                            "first_greet_date": now_local.date().isoformat(),
                            "age": age_value or "",
                            "city": self._extract_city(candidate),
                            "expected_job": self._extract_expected_job(candidate),
                            "followup_key": self._build_followup_key(candidate),
                            "has_contact": False,
                            "followup_status": "pending",
                        },
                    )

                    proactive_sent = self._send_proactive_once_then_close(candidate_id=candidate_id)
                    if proactive_sent:
                       logging.info("hunter proactive message sent candidate_id=%s", candidate_id)
                    elif self.proactive_enabled and self.proactive_template:
                      logging.error("hunter proactive message failed candidate_id=%s", candidate_id)

                # 处理完必清理，绝对杜绝残留弹窗挡住下一个人
                self._close_chat_panel()
                self._dismiss_blocking_dialog()

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
                    card_scope = btn.locator(
                        "xpath=./ancestor::*[contains(@class, 'card') or contains(@class, 'item')][1]"
                    ).first
                    if card_scope.count() == 0:
                        card_scope = btn
                    opened_chat = self._open_chat_after_greet(
                        card_scope,
                        allow_global_fallback=True,
                    )
                    open_chat_attempted += 1
                    proactive_sent = False
                    if opened_chat:
                        open_chat_success += 1
                        proactive_sent = self._send_proactive_once_then_close(candidate_id=f"fallback-{i}")
                    if proactive_sent:
                        logging.info("hunter proactive message sent candidate_id=fallback-%s", i)
                    elif self.proactive_enabled and self.proactive_template:
                        logging.error("hunter proactive message failed candidate_id=fallback-%s", i)
                    self._close_chat_panel()
                except Error:
                    self._close_chat_panel()
                    continue

        open_rate = 0.0 if open_chat_attempted == 0 else (open_chat_success / open_chat_attempted) * 100.0
        logging.info(
            "hunter round greeted=%s open_chat=%s/%s rate=%.2f%%",
            greeted,
            open_chat_success,
            open_chat_attempted,
            open_rate,
        )
        return greeted
