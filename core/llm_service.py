import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

KB_PATH = Path("config/station_kb.txt")
SYSTEM_PROMPT_TEMPLATE = """你是一个正在招聘外卖骑手的站点招聘专员。
你的目标是自然、礼貌地推进沟通，并尽量在对话中引导对方留下手机号或微信号。

规则：
1) 回复要短，尽量 1-2 句，口语化，不要像机器人。
2) 如果候选人问到薪资、住宿、车辆、出勤等问题，只能基于站点知识库回答，不要编造。
3) 在候选人有兴趣时，顺势询问联系方式（微信或手机号）。
4) 如果候选人明确拒绝或辱骂，礼貌结束，不要持续追问。

站点知识库：
{kb}
"""


def _load_kb_text() -> str:
    if KB_PATH.exists():
        return KB_PATH.read_text(encoding="utf-8")
    return "暂无站点知识库信息。"


def _build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def generate_reply(chat_history: List[Dict[str, str]]) -> str:
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    kb = _load_kb_text()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(kb=kb)
    client = _build_client()

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=120,
    )
    return completion.choices[0].message.content.strip()
