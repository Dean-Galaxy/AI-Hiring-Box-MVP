import os
import re
from typing import Dict, Optional

import requests

from utils.storage import load_contacted_map, save_contacted_map


PHONE_REGEX = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
WECHAT_KEYWORD_REGEX = re.compile(
    r"(?:微信|vx|v信|wechat|wx)[：:\s]*([a-zA-Z][-_a-zA-Z0-9]{5,19})",
    flags=re.IGNORECASE,
)
WECHAT_RAW_REGEX = re.compile(r"\b[a-zA-Z][-_a-zA-Z0-9]{5,19}\b")


def check_for_lead(candidate_message: str) -> Optional[str]:
    phone_match = PHONE_REGEX.search(candidate_message)
    if phone_match:
        return phone_match.group(1)

    wechat_match = WECHAT_KEYWORD_REGEX.search(candidate_message)
    if wechat_match:
        return wechat_match.group(1)

    # Fallback for plain IDs like "abc12345" without keyword.
    if "微信" in candidate_message or "wx" in candidate_message.lower():
        raw_match = WECHAT_RAW_REGEX.search(candidate_message)
        if raw_match:
            return raw_match.group(0)

    return None


def send_to_webhook(candidate_name: str, contact: str, candidate_id: str) -> bool:
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    webhook_token = os.getenv("FEISHU_WEBHOOK_TOKEN", "").strip()
    headers = {"Content-Type": "application/json"}
    if webhook_token:
        headers["X-Webhook-Token"] = webhook_token

    payload = {
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "contact": contact,
    }
    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
    except requests.RequestException:
        return False
    return response.status_code < 300


def mark_candidate_converted(candidate_id: str, contact: str) -> None:
    data = load_contacted_map()
    candidate = data.get(candidate_id, {})
    candidate["status"] = "converted"
    candidate["lead"] = contact
    data[candidate_id] = candidate
    save_contacted_map(data)


def is_converted(candidate_id: str) -> bool:
    data = load_contacted_map()
    return data.get(candidate_id, {}).get("status") == "converted"
