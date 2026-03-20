import os
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from playwright.sync_api import Error, Page

from core.browser_manager import random_sleep
from core.notify import send_feishu_text
from utils.storage import (
    load_contacted_map,
    load_system_state,
    save_contacted_map,
    save_system_state,
)


DEFAULT_FOLLOWUP_TEXT = (
    "你好呀，最近工作落实了吗？咱们站点还在招人，有人带，最快当天就能跑单赚钱。"
    "还没定下来的话发个联系方式给我，我给你详细说说？你先了解着，不来也没关系的。"
)


@dataclass
class FollowUpConfig:
    enabled: bool
    timezone: str
    feature_start_date: str
    text: str
    daily_limit: int
    interval_min_sec: float
    interval_max_sec: float
    retry_after_fail: int
    max_retry_days: int
    run_hour: int
    run_minute: int
    report_hour: int
    report_minute: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_followup_config() -> FollowUpConfig:
    tz = os.getenv("FOLLOWUP_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
    now_local = datetime.now(ZoneInfo(tz)).date().isoformat()
    return FollowUpConfig(
        enabled=_env_bool("FOLLOWUP_ENABLED", True),
        timezone=tz,
        feature_start_date=os.getenv("FOLLOWUP_FEATURE_START_DATE", now_local).strip() or now_local,
        text=os.getenv("FOLLOWUP_MESSAGE_TEMPLATE", DEFAULT_FOLLOWUP_TEXT).strip() or DEFAULT_FOLLOWUP_TEXT,
        daily_limit=max(1, _env_int("FOLLOWUP_DAILY_LIMIT", 30)),
        interval_min_sec=max(0.5, _env_float("FOLLOWUP_INTERVAL_MIN_SEC", 3.0)),
        interval_max_sec=max(0.6, _env_float("FOLLOWUP_INTERVAL_MAX_SEC", 8.0)),
        retry_after_fail=max(0, _env_int("FOLLOWUP_IMMEDIATE_RETRY", 2)),
        max_retry_days=max(0, _env_int("FOLLOWUP_MAX_RETRY_DAYS", 1)),
        run_hour=_env_int("FOLLOWUP_RUN_HOUR", 10),
        run_minute=_env_int("FOLLOWUP_RUN_MINUTE", 0),
        report_hour=_env_int("FOLLOWUP_REPORT_HOUR", 20),
        report_minute=_env_int("FOLLOWUP_REPORT_MINUTE", 0),
    )


def now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def _parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _has_contact(record: Dict[str, Any]) -> bool:
    lead = str(record.get("lead", "")).strip()
    if lead:
        return True
    return bool(record.get("has_contact"))


def _eligible_records(
    data: Dict[str, Dict[str, Any]],
    cfg: FollowUpConfig,
    today: date,
) -> List[Tuple[str, Dict[str, Any]]]:
    eligible: List[Tuple[str, Dict[str, Any]]] = []
    launch_date = _parse_date(cfg.feature_start_date) or today
    for candidate_id, rec in data.items():
        if _has_contact(rec):
            continue
        status = str(rec.get("followup_status", "")).strip()
        if status in {"sent", "retry_failed"}:
            continue

        first_date = _parse_date(str(rec.get("first_greet_date", "")).strip())
        if not first_date or first_date < launch_date:
            continue
        due = first_date + timedelta(days=7)
        rec["followup_due_date"] = due.isoformat()
        if today < due:
            continue

        retry_date = _parse_date(str(rec.get("followup_retry_date", "")).strip())
        if status == "retry_pending" and retry_date and today < retry_date:
            continue
        if status == "retry_pending" and retry_date and today > retry_date + timedelta(days=cfg.max_retry_days):
            rec["followup_status"] = "retry_failed"
            rec["followup_error"] = "retry window expired"
            continue

        rec.setdefault("followup_status", "pending")
        rec.setdefault("followup_total_attempts", 0)
        rec.setdefault("followup_retry_used", 0)
        rec.setdefault("queue_entered_at", now_local(cfg.timezone).isoformat(timespec="seconds"))
        eligible.append((candidate_id, rec))

    eligible.sort(
        key=lambda item: (
            item[1].get("first_greet_date", "9999-99-99"),
            item[1].get("queue_entered_at", "9999-99-99T99:99:99"),
        )
    )
    return eligible


def _open_chat_thread(page: Page, candidate_id: str, candidate_name: str) -> bool:
    locator_by_id = page.locator(f".chat-item[data-geek-id='{candidate_id}'], .chat-item[data-id='{candidate_id}']")
    if locator_by_id.count() > 0:
        locator_by_id.first.click()
        random_sleep(0.6, 1.2)
        return True
    if candidate_name:
        locator_by_name = page.locator(f".chat-item:has-text('{candidate_name}')")
        if locator_by_name.count() > 0:
            locator_by_name.first.click()
            random_sleep(0.6, 1.2)
            return True
    return False


def _send_text(page: Page, text: str) -> bool:
    textarea_selector = "textarea.chat-input"
    editable_selector = "div[contenteditable='true']"
    if page.locator(textarea_selector).count() > 0:
        area = page.locator(textarea_selector).first
        area.click()
        area.fill(text)
    elif page.locator(editable_selector).count() > 0:
        area = page.locator(editable_selector).first
        area.click()
        page.keyboard.type(text, delay=random.randint(60, 150))
    else:
        return False

    send_btn = page.locator("button:has-text('发送')")
    if send_btn.count() > 0:
        send_btn.first.click()
    else:
        page.keyboard.press("Enter")
    random_sleep(0.5, 1.0)
    return True


def _is_send_success(page: Page) -> bool:
    my_messages = page.locator(".message-item.me")
    if my_messages.count() == 0:
        return False
    try:
        latest = my_messages.last.inner_text().strip()
    except Error:
        return False
    return bool(latest)


def _send_one_candidate(
    page: Page,
    candidate_id: str,
    rec: Dict[str, Any],
    cfg: FollowUpConfig,
) -> Tuple[bool, str]:
    name = str(rec.get("name", "")).strip()
    try:
        opened = _open_chat_thread(page, candidate_id=candidate_id, candidate_name=name)
        if not opened:
            return False, "chat thread not found"
        sent = _send_text(page, cfg.text)
        if not sent:
            return False, "input or send control not found"
        if not _is_send_success(page):
            return False, "message not shown in chat"
        return True, ""
    except Error:
        return False, "playwright error"


def _upsert_daily_metrics(state: Dict[str, Any], date_key: str) -> Dict[str, Any]:
    daily = state.setdefault("daily_metrics", {})
    metrics = daily.setdefault(
        date_key,
        {
            "planned_total": 0,
            "deferred_by_cap": 0,
            "skipped_by_switch": 0,
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "retry_failed": 0,
            "failure_reasons": {},
        },
    )
    return metrics


def run_followup_once(page: Page, inbox_url: str, manual: bool = False) -> Dict[str, Any]:
    cfg = get_followup_config()
    now_dt = now_local(cfg.timezone)
    today_key = now_dt.date().isoformat()
    state = load_system_state()
    last_date = str(state.get("last_followup_run_date", "")).strip()
    if not manual and last_date == today_key:
        return {"ran": False, "reason": "already_ran_today"}

    data = load_contacted_map()
    eligible = _eligible_records(data, cfg=cfg, today=now_dt.date())
    metrics = _upsert_daily_metrics(state, today_key)
    metrics["planned_total"] = len(eligible)

    if not cfg.enabled and not manual:
        metrics["skipped_by_switch"] = len(eligible)
        state["last_followup_run_date"] = today_key
        save_system_state(state)
        save_contacted_map(data)
        return {"ran": True, "reason": "switch_off", "planned": len(eligible)}

    run_queue = eligible[: cfg.daily_limit]
    deferred = max(0, len(eligible) - len(run_queue))
    metrics["deferred_by_cap"] = deferred

    page.goto(inbox_url, wait_until="domcontentloaded")
    random_sleep(0.8, 1.6)
    reasons = Counter()
    for idx, (candidate_id, rec) in enumerate(run_queue):
        ok = False
        reason = "unknown"
        for _ in range(cfg.retry_after_fail + 1):
            metrics["attempted"] += 1
            rec["followup_total_attempts"] = int(rec.get("followup_total_attempts", 0)) + 1
            ok, reason = _send_one_candidate(page, candidate_id, rec, cfg)
            if ok:
                break
            random_sleep(0.8, 1.4)

        if ok:
            rec["followup_status"] = "sent"
            rec["followup_sent_at"] = now_local(cfg.timezone).isoformat(timespec="seconds")
            metrics["success"] += 1
        else:
            metrics["failed"] += 1
            reasons[reason] += 1
            retry_used = int(rec.get("followup_retry_used", 0))
            if retry_used < cfg.max_retry_days:
                rec["followup_retry_used"] = retry_used + 1
                rec["followup_retry_date"] = (now_dt.date() + timedelta(days=1)).isoformat()
                rec["followup_status"] = "retry_pending"
                rec["followup_error"] = reason
            else:
                rec["followup_status"] = "retry_failed"
                rec["followup_error"] = reason
                metrics["retry_failed"] += 1

        if idx < len(run_queue) - 1:
            random_sleep(cfg.interval_min_sec, max(cfg.interval_min_sec, cfg.interval_max_sec))

    reason_bucket = metrics.setdefault("failure_reasons", {})
    for key, value in reasons.items():
        reason_bucket[key] = int(reason_bucket.get(key, 0)) + int(value)

    state["last_followup_run_date"] = today_key
    save_contacted_map(data)
    save_system_state(state)
    return {"ran": True, "planned": len(eligible), "executed": len(run_queue), "deferred": deferred}


def build_daily_report_text(report_date: str) -> str:
    state = load_system_state()
    metrics = state.get("daily_metrics", {}).get(report_date, {})
    planned = int(metrics.get("planned_total", 0))
    deferred = int(metrics.get("deferred_by_cap", 0))
    skipped = int(metrics.get("skipped_by_switch", 0))
    success = int(metrics.get("success", 0))
    retry_failed = int(metrics.get("retry_failed", 0))
    reasons = metrics.get("failure_reasons", {}) or {}
    involved_people = success + int(metrics.get("failed", 0))

    denominator = planned - deferred - skipped
    if denominator <= 0:
        success_rate = 100.0
    else:
        success_rate = (success / denominator) * 100

    top_reasons = sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:3]
    reason_text = "、".join([f"{k}:{v}" for k, v in top_reasons]) if top_reasons else "无"

    return (
        f"【二次问候日报】{report_date}\n"
        f"- 补发失败总次数: {retry_failed}\n"
        f"- 涉及候选人数: {involved_people}\n"
        f"- 失败原因Top3: {reason_text}\n"
        f"- 当天二次问候发送成功率: {success_rate:.2f}%"
    )


def maybe_send_daily_report() -> Dict[str, Any]:
    cfg = get_followup_config()
    now_dt = now_local(cfg.timezone)
    date_key = now_dt.date().isoformat()
    state = load_system_state()
    last_report_date = str(state.get("last_report_date", "")).strip()
    if last_report_date == date_key:
        return {"sent": False, "reason": "already_sent_today"}

    text = build_daily_report_text(date_key)
    sent = send_feishu_text(text)
    state["last_report_date"] = date_key
    state["last_report_sent"] = bool(sent)
    save_system_state(state)
    return {"sent": sent, "date": date_key}


def should_run_followup_now() -> bool:
    cfg = get_followup_config()
    now_dt = now_local(cfg.timezone)
    return now_dt.hour == cfg.run_hour and now_dt.minute >= cfg.run_minute


def should_send_report_now() -> bool:
    cfg = get_followup_config()
    now_dt = now_local(cfg.timezone)
    return now_dt.hour == cfg.report_hour and now_dt.minute >= cfg.report_minute
