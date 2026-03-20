import os
import logging
import re
from typing import Dict, List, Optional

from playwright.sync_api import Error, Page

from core.browser_manager import human_type, random_sleep
from core.extractor import check_for_lead, is_converted, mark_candidate_converted, send_to_webhook
from core.llm_service import generate_reply
from utils.storage import upsert_candidate_status


class Farmer:
    def __init__(self, page: Page, inbox_url: str):
        self.page = page
        self.inbox_url = inbox_url
        self.debug_current_chat = os.getenv("FARMER_DEBUG_CURRENT_CHAT", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _candidate_key(self, candidate_id: str, candidate_name: str) -> str:
        cid = (candidate_id or "").strip()
        if cid:
            return cid
        cname = re.sub(r"\s+", "", (candidate_name or "").strip())
        return f"name:{cname}" if cname else ""

    def _is_meta_converted(self, meta: Dict[str, str]) -> bool:
        key = self._candidate_key(meta.get("candidate_id", ""), meta.get("candidate_name", ""))
        if not key:
            return False
        return is_converted(key)

    def navigate_inbox(self) -> None:
        self._pick_working_page()
        current_url = (self.page.url or "").strip()
        logging.info("farmer current_url=%s", current_url)
        self.page.goto(self.inbox_url, wait_until="domcontentloaded")
        random_sleep(1.0, 2.0)

    def _pick_working_page(self) -> None:
        pages = self.page.context.pages
        if not pages:
            return
        for p in reversed(pages):
            url = (p.url or "").strip()
            if "/web/chat/index" in url:
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

    def _switch_tab(self, label: str) -> bool:
        tabs = self.page.locator(".chat-label-item")
        total = tabs.count()
        for i in range(total):
            tab = tabs.nth(i)
            try:
                title = (tab.get_attribute("title") or "").strip()
            except Error:
                title = ""
            try:
                text = tab.inner_text().strip()
            except Error:
                text = ""
            tab_label = f"{title} {text}".strip()
            if label not in tab_label:
                continue
            try:
                tab_class = (tab.get_attribute("class") or "").lower()
                aria_selected = (tab.get_attribute("aria-selected") or "").strip().lower()
                already_selected = "selected" in tab_class or "active" in tab_class or aria_selected == "true"
                if not already_selected:
                    tab.click(timeout=1500)
                random_sleep(0.6, 1.1)
                has_dot = tab.locator(".badge-dot").count() > 0
                logging.info("farmer switched tab=%s has_dot=%s", label, has_dot)
                self._scroll_thread_list_to_top()
                return True
            except Error:
                continue
        logging.info("farmer switch tab failed tab=%s total_tabs=%s", label, total)
        return False

    def _thread_locator(self):
        return self.page.locator(".geek-item-wrap")

    def _thread_list_container(self):
        selectors = [
            ".friend-list",
            ".chat-user-list",
            ".geek-list",
            ".list-wrap",
            ".list-content",
            ".chat-list",
        ]
        for selector in selectors:
            node = self.page.locator(selector).first
            if node.count() == 0:
                continue
            try:
                if node.is_visible():
                    return node
            except Error:
                continue
        return None

    def _scroll_thread_list_once(self, delta_y: int = 700) -> None:
        container = self._thread_list_container()
        if container is not None:
            try:
                container.hover(timeout=800)
            except Error:
                pass
        self.page.mouse.wheel(0, delta_y)
        random_sleep(0.25, 0.45)

    def _scroll_thread_list_to_top(self) -> None:
        for _ in range(3):
            self._scroll_thread_list_once(delta_y=-1200)

    def _is_left_panel_thread(self, thread) -> bool:
        try:
            box = thread.bounding_box()
        except Error:
            return False
        if not box:
            return False
        x = float(box.get("x", 9999))
        y = float(box.get("y", 0))
        w = float(box.get("width", 0))
        h = float(box.get("height", 0))
        if x > 460:
            return False
        if y < 130:
            return False
        if w < 120 or h < 24:
            return False
        return True

    def _thread_meta(self, thread) -> Dict[str, str]:
        candidate_id = thread.get_attribute("data-geek-id") or thread.get_attribute("data-id") or ""
        name_locator = thread.locator(".name, .geek-name, [class*='name']").first
        if name_locator.count():
            candidate_name = name_locator.inner_text().strip()
        else:
            try:
                raw = thread.inner_text().strip()
            except Error:
                raw = ""
            candidate_name = re.split(r"[\n\r]", raw)[0].strip() if raw else ""
        return {"candidate_id": candidate_id, "candidate_name": candidate_name}

    def _badge_count_value(self, thread) -> int:
        badge_selectors = [
            ".badge-count",
            "[class*='badge-count']",
            ".badge:has(.count)",
            "[class*='unread-count']",
        ]
        for selector in badge_selectors:
            badge = thread.locator(selector)
            if badge.count() == 0:
                continue
            try:
                node = badge.first
                if not node.is_visible():
                    continue
                text = (node.inner_text() or "").strip()
            except Error:
                continue
            match = re.search(r"\d+", text)
            if not match:
                continue
            try:
                return int(match.group(0))
            except ValueError:
                continue
        return 0

    def _thread_has_unread_badge(self, thread) -> bool:
        if self._badge_count_value(thread) > 0:
            return True
        # Some accounts show unread as red dot without number.
        dot = thread.locator(".badge-dot, [class*='badge-dot'], [class*='unread-dot']")
        if dot.count() == 0:
            return False
        try:
            return dot.first.is_visible()
        except Error:
            return False

    def _has_pending_candidate_message(self) -> bool:
        friend_bubbles = self.page.locator(".item-friend")
        if friend_bubbles.count() > 0:
            try:
                latest = friend_bubbles.last.inner_text().strip()
                return bool(latest)
            except Error:
                return False
        bubbles = self.page.locator(".message-item")
        if bubbles.count() == 0:
            return False
        try:
            latest_class = bubbles.last.get_attribute("class") or ""
        except Error:
            return False
        return "me" not in latest_class

    def _open_top_unread_current_tab(self) -> Optional[Dict[str, str]]:
        unread_found = 0
        scanned_keys = set()
        max_scroll_pages = 10

        for page_idx in range(max_scroll_pages):
            threads = self._thread_locator()
            total = threads.count()
            for i in range(total):
                thread = threads.nth(i)
                if not self._is_left_panel_thread(thread):
                    continue
                if not self._thread_has_unread_badge(thread):
                    continue
                meta = self._thread_meta(thread)
                key = self._candidate_key(meta.get("candidate_id", ""), meta.get("candidate_name", ""))
                if key in scanned_keys:
                    continue
                scanned_keys.add(key)
                unread_count = max(1, self._badge_count_value(thread))
                unread_found += 1
                if self._is_meta_converted(meta):
                    logging.info("farmer skip converted unread key=%s", key)
                    continue
                try:
                    thread.scroll_into_view_if_needed(timeout=1200)
                    thread.click(timeout=1500)
                    random_sleep(0.8, 1.6)
                except Error:
                    try:
                        thread.click(timeout=1500, force=True)
                        random_sleep(0.8, 1.6)
                    except Error:
                        continue
                if self._has_pending_candidate_message():
                    logging.info("farmer unread hit page=%s unread_count=%s key=%s", page_idx, unread_count, key)
                    return meta
                # Even if bubble check fails, unread badge itself is enough to process.
                logging.info("farmer unread hit without bubble-check page=%s key=%s", page_idx, key)
                return meta
            if page_idx < max_scroll_pages - 1:
                self._scroll_thread_list_once(delta_y=700)
        logging.info("farmer unread candidates in tab=%s", unread_found)
        return None

    def _open_first_pending_by_history(self, max_scan: int = 20) -> Optional[Dict[str, str]]:
        threads = self._thread_locator()
        total = min(threads.count(), max_scan)
        logging.info("farmer scan history threads=%s", total)
        for i in range(total):
            thread = threads.nth(i)
            if not self._is_left_panel_thread(thread):
                continue
            meta = self._thread_meta(thread)
            if self._is_meta_converted(meta):
                continue
            try:
                thread.scroll_into_view_if_needed(timeout=1200)
                thread.click(timeout=1500)
                random_sleep(0.7, 1.4)
            except Error:
                try:
                    thread.click(timeout=1500, force=True)
                    random_sleep(0.7, 1.4)
                except Error:
                    continue
            if self._has_pending_candidate_message():
                return meta
        return None

    def _open_by_avatar_badge(self, max_scan: int = 30) -> Optional[Dict[str, str]]:
        threads = self._thread_locator()
        total = min(threads.count(), max_scan)
        matched = 0
        for i in range(total):
            thread = threads.nth(i)
            if not self._is_left_panel_thread(thread):
                continue
            if not self._thread_has_unread_badge(thread):
                continue
            matched += 1
            meta = self._thread_meta(thread)
            if self._is_meta_converted(meta):
                continue
            try:
                thread.scroll_into_view_if_needed(timeout=1200)
                thread.click(timeout=1500)
                random_sleep(0.7, 1.3)
            except Error:
                try:
                    thread.click(timeout=1500, force=True)
                    random_sleep(0.7, 1.3)
                except Error:
                    continue
            logging.info("farmer avatar-badge matched=%s", matched)
            return meta
        logging.info("farmer avatar-badge matched=%s", matched)
        return None

    def _open_top_unread(self) -> Optional[Dict[str, str]]:
        # Pass 1: strictly scan unread in all tabs first.
        for label in ("新招呼", "沟通中", "全部"):
            switched = self._switch_tab(label)
            if not switched:
                continue
            chat_meta = self._open_top_unread_current_tab()
            if chat_meta:
                logging.info("farmer picked unread thread tab=%s candidate=%s", label, chat_meta.get("candidate_name", ""))
                return chat_meta

            # Fallback 1.5: unread badge selector may miss on some account UIs.
            chat_meta = self._open_by_avatar_badge(max_scan=40)
            if chat_meta:
                logging.info("farmer picked unread-by-avatar tab=%s candidate=%s", label, chat_meta.get("candidate_name", ""))
                return chat_meta

        # Pass 2: no unread found, then fallback to pending-by-history.
        for label in ("全部", "沟通中", "新招呼"):
            switched = self._switch_tab(label)
            if not switched:
                continue
            chat_meta = self._open_first_pending_by_history(max_scan=40)
            if chat_meta:
                logging.info("farmer picked pending-by-history tab=%s candidate=%s", label, chat_meta.get("candidate_name", ""))
                return chat_meta
        return None

    def _current_chat_meta_for_debug(self) -> Optional[Dict[str, str]]:
        # Debug-only fallback: use currently selected left thread if available.
        threads = self._thread_locator()
        total = min(threads.count(), 200)
        for i in range(total):
            thread = threads.nth(i)
            if not self._is_left_panel_thread(thread):
                continue
            try:
                css = (thread.get_attribute("class") or "").lower()
            except Error:
                css = ""
            aria_selected = ""
            try:
                aria_selected = (thread.get_attribute("aria-selected") or "").strip().lower()
            except Error:
                aria_selected = ""
            if not any(flag in css for flag in ("active", "selected", "cur", "current")) and aria_selected != "true":
                continue
            meta = self._thread_meta(thread)
            logging.info("farmer debug selected-thread meta=%s", meta)
            return meta

        # Last fallback: if the right panel has candidate bubble(s), allow debug run.
        if self.page.locator(".item-friend, .message-item:not(.me)").count() > 0:
            logging.info("farmer debug fallback to right-panel-only")
            return {"candidate_id": "debug-current-chat", "candidate_name": "当前会话(调试)"}
        return None

    def extract_chat_history(self, limit: int = 5) -> List[Dict[str, str]]:
        bubbles = self.page.locator(".message-item")
        total = bubbles.count()
        start = max(0, total - limit)

        messages: List[Dict[str, str]] = []
        for i in range(start, total):
            bubble = bubbles.nth(i)
            text = bubble.inner_text().strip()
            sender_is_me = "me" in (bubble.get_attribute("class") or "")
            messages.append(
                {
                    "role": "assistant" if sender_is_me else "user",
                    "content": text,
                }
            )
        return messages

    def _latest_candidate_message(self) -> str:
        bubbles = self.page.locator(".item-friend")
        if bubbles.count() == 0:
            bubbles = self.page.locator(".message-item:not(.me)")
        if bubbles.count() == 0:
            return ""
        return bubbles.last.inner_text().strip()

    def _click_any(self, locator) -> bool:
        total = locator.count()
        for i in range(total):
            target = locator.nth(i)
            try:
                if not target.is_visible():
                    continue
                target.scroll_into_view_if_needed(timeout=800)
                target.click(timeout=1200)
                return True
            except Error:
                try:
                    target.click(timeout=1200, force=True)
                    return True
                except Error:
                    continue
        return False

    def _accept_exchange_wechat(self) -> bool:
        clicked = False

        # Blue reminder bar: "我想要和您交换微信，您是否同意"
        blue_notice_buttons = self.page.locator(
            ".notice-list.notice-blue-list:has-text('交换微信') .op a.btn, "
            ".notice-list.notice-blue-list:has-text('交换微信') .op a:has-text('同意')"
        )
        if self._click_any(blue_notice_buttons):
            clicked = True
            logging.info("farmer clicked wechat agree via blue notice")
            random_sleep(0.3, 0.8)

        # Green message card with WeChat icon.
        wechat_cards = self.page.locator(
            ".message-card-wrap:has(.message-dialog-icon-weixin):has-text('交换微信')"
        )
        if wechat_cards.count() == 0:
            wechat_cards = self.page.locator(".message-card-wrap:has(.message-dialog-icon-weixin)")

        total = wechat_cards.count()
        for i in range(total - 1, -1, -1):
            card = wechat_cards.nth(i)
            agree_buttons = card.locator(
                ".message-card-buttons .card-btn:has-text('同意'), "
                ".message-card-buttons .card-btn[d-c]"
            )
            if self._click_any(agree_buttons):
                clicked = True
                logging.info("farmer clicked wechat agree via green card")
                random_sleep(0.3, 0.8)
                break
        return clicked

    def _extract_lead_from_chat(self) -> Optional[str]:
        snippets: List[str] = []
        seen = set()

        def collect(text: str) -> None:
            cleaned = re.sub(r"\s+", " ", (text or "").strip())
            if not cleaned or cleaned in seen:
                return
            seen.add(cleaned)
            snippets.append(cleaned)

        collect(self._latest_candidate_message())

        selectors = [
            ".message-card-wrap:has(.message-dialog-icon-contact) .message-card-top-title",
            ".item-friend .message-card-top-title",
            ".item-friend",
            ".message-item:not(.me)",
            ".notice-list.notice-blue-list",
        ]

        for selector in selectors:
            nodes = self.page.locator(selector)
            total = nodes.count()
            start = max(0, total - 10)
            for i in range(total - 1, start - 1, -1):
                try:
                    text = nodes.nth(i).inner_text().strip()
                except Error:
                    continue
                collect(text)

        for text in snippets:
            lead = check_for_lead(text)
            if lead:
                logging.info("farmer lead extracted lead=%s", lead)
                return lead
        return None

    def type_and_send(self, text: str) -> bool:
        textarea_selector = "textarea.chat-input"
        contenteditable_selector = "div[contenteditable='true']"
        if self.page.locator(f"{textarea_selector}, {contenteditable_selector}").count() == 0:
            return False

        if self.page.locator(textarea_selector).count() > 0:
            human_type(self.page, text, target_selector=textarea_selector)
        else:
            target = self.page.locator(contenteditable_selector).first
            target.click()
            human_type(self.page, text)
        random_sleep(0.4, 1.0)

        send_btn = self.page.locator("button:has-text('发送')")
        if send_btn.count():
            send_btn.first.click()
        else:
            self.page.keyboard.press("Enter")
        return True

    def process_once(self) -> bool:
        debug_current_chat = False
        chat_meta: Optional[Dict[str, str]] = None
        if self.debug_current_chat:
            chat_meta = self._current_chat_meta_for_debug()
            debug_current_chat = bool(chat_meta)
            if debug_current_chat:
                logging.info("farmer debug current chat fallback candidate=%s", chat_meta.get("candidate_name", ""))
        if not chat_meta:
            chat_meta = self._open_top_unread()
        if not chat_meta:
            return False

        candidate_id = chat_meta["candidate_id"] or chat_meta["candidate_name"]
        candidate_name = chat_meta["candidate_name"]
        candidate_key = self._candidate_key(candidate_id, candidate_name)

        if candidate_key and is_converted(candidate_key):
            logging.info("farmer skip already converted key=%s", candidate_key)
            return True

        accepted_wechat = self._accept_exchange_wechat()
        if accepted_wechat:
            random_sleep(0.6, 1.1)

        lead = self._extract_lead_from_chat()
        if lead:
            webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
            pushed = send_to_webhook(candidate_name, lead, candidate_id)
            upsert_candidate_status(
                candidate_key or candidate_id,
                {
                    "name": candidate_name,
                    "has_contact": True,
                    "lead": lead,
                    "followup_status": "sent",
                },
            )
            if webhook_url and not pushed:
                # Webhook configured but push failed: keep conversation for webhook retry.
                return False
            mark_candidate_converted(candidate_key or candidate_id, lead)
            return True

        if accepted_wechat:
            # After agreeing exchange, platform may emit contact card asynchronously.
            return True

        if debug_current_chat:
            # Debug mode is for validating card extraction/agree-click only.
            # Avoid sending LLM replies to already-open chats during manual testing.
            return False

        history = self.extract_chat_history(limit=5)
        try:
            reply = generate_reply(history)
        except Exception:
            return False

        sent = self.type_and_send(reply)
        if sent:
            upsert_candidate_status(candidate_id, {"name": candidate_name, "status": "contacted"})
        return sent

    def process_unread(self, max_rounds: int = 20) -> int:
        count = 0
        misses = 0
        miss_limit = 8 if self.debug_current_chat else 2
        for _ in range(max_rounds):
            try:
                handled = self.process_once()
            except Error:
                break
            if not handled:
                misses += 1
                if misses >= miss_limit:
                    break
                random_sleep(0.4, 0.8)
                continue
            misses = 0
            count += 1
            random_sleep(0.8, 1.8)
        return count
