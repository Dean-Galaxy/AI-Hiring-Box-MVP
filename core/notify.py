import os
from typing import Optional

import requests


def send_feishu_text(text: str, webhook_url: Optional[str] = None) -> bool:
    url = (webhook_url or os.getenv("FEISHU_BOT_WEBHOOK_URL", "")).strip()
    if not url:
        return False
    payload = {"msg_type": "text", "content": {"text": text}}
    try:
        resp = requests.post(url, json=payload, timeout=10)
    except requests.RequestException:
        return False
    return resp.status_code < 300
