from typing import Dict, List, Optional

from playwright.sync_api import Error, Page

from core.browser_manager import random_sleep
from core.extractor import check_for_lead, is_converted, mark_candidate_converted, send_to_webhook
from core.llm_service import generate_reply
from utils.storage import upsert_candidate_status


class Farmer:
    def __init__(self, page: Page, inbox_url: str):
        self.page = page
        self.inbox_url = inbox_url

    def navigate_inbox(self) -> None:
        self.page.goto(self.inbox_url, wait_until="domcontentloaded")
        random_sleep(1.0, 2.0)

    def _open_top_unread(self) -> Optional[Dict[str, str]]:
        unread_threads = self.page.locator(".chat-item.unread, .chat-item:has(.red-dot)")
        if unread_threads.count() == 0:
            return None

        for i in range(unread_threads.count()):
            thread = unread_threads.nth(i)
            candidate_id = thread.get_attribute("data-geek-id") or thread.get_attribute("data-id") or ""
            candidate_name = (
                thread.locator(".name").first.inner_text().strip()
                if thread.locator(".name").count()
                else "未知候选人"
            )
            if candidate_id and is_converted(candidate_id):
                continue

            thread.click()
            random_sleep(0.8, 1.8)
            return {"candidate_id": candidate_id, "candidate_name": candidate_name}
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
        bubbles = self.page.locator(".message-item:not(.me)")
        if bubbles.count() == 0:
            return ""
        return bubbles.last.inner_text().strip()

    def type_and_send(self, text: str) -> bool:
        textarea_selector = "textarea.chat-input"
        contenteditable_selector = "div[contenteditable='true']"
        if self.page.locator(f"{textarea_selector}, {contenteditable_selector}").count() == 0:
            return False

        if self.page.locator(textarea_selector).count() > 0:
            self.page.click(textarea_selector)
            self.page.type(textarea_selector, text, delay=100)
        else:
            target = self.page.locator(contenteditable_selector).first
            target.click()
            self.page.keyboard.type(text, delay=100)
        random_sleep(0.4, 1.0)

        send_btn = self.page.locator("button:has-text('发送')")
        if send_btn.count():
            send_btn.first.click()
        else:
            self.page.keyboard.press("Enter")
        return True

    def process_once(self) -> bool:
        chat_meta = self._open_top_unread()
        if not chat_meta:
            return False

        candidate_id = chat_meta["candidate_id"] or chat_meta["candidate_name"]
        candidate_name = chat_meta["candidate_name"]

        latest_message = self._latest_candidate_message()
        lead = check_for_lead(latest_message)
        if lead:
            send_to_webhook(candidate_name, lead, candidate_id)
            mark_candidate_converted(candidate_id, lead)
            return True

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
        for _ in range(max_rounds):
            try:
                handled = self.process_once()
            except Error:
                break
            if not handled:
                break
            count += 1
            random_sleep(0.8, 1.8)
        return count
