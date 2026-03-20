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
QQ_KEYWORD_REGEX = re.compile(
    r"(?:qq|扣扣|企鹅号?)[：:\s]*([1-9][0-9\s-]{4,20})",
    flags=re.IGNORECASE,
)


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

    qq_match = QQ_KEYWORD_REGEX.search(candidate_message)
    if qq_match:
        normalized_qq = re.sub(r"\D", "", qq_match.group(1))
        if re.fullmatch(r"[1-9]\d{4,11}", normalized_qq):
            return normalized_qq

    return None


def send_to_webhook(candidate_name: str, contact: str, candidate_id: str) -> bool:
    # 你的万能中转站地址（也就是上面那个 workers.dev 链接）
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    # 你在 Cloudflare 配置的防护 Token
    webhook_token = os.getenv("FEISHU_WEBHOOK_TOKEN", "").strip()
    headers = {"Content-Type": "application/json"}
    if webhook_token:
        headers["X-Webhook-Token"] = webhook_token

    # 核心变化：在这里把本地 .env 里读取到的该客户的专属飞书凭证打包发过去
    payload = {
        "candidate_id": candidate_id,
        "candidate_name": candidate_name,
        "contact": contact,
        "feishu_app_id": os.getenv("FEISHU_APP_ID", "").strip(),
        "feishu_app_secret": os.getenv("FEISHU_APP_SECRET", "").strip(),
        "feishu_app_token": os.getenv("FEISHU_APP_TOKEN", "").strip(),
        "feishu_table_id": os.getenv("FEISHU_TABLE_ID", "").strip(),
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
    candidate["has_contact"] = True
    candidate["followup_status"] = "sent"
    data[candidate_id] = candidate
    save_contacted_map(data)


def is_converted(candidate_id: str) -> bool:
    data = load_contacted_map()
    return data.get(candidate_id, {}).get("status") == "converted"
