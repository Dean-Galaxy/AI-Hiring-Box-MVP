import json
from pathlib import Path
from typing import Any, Dict


CONTACTED_PATH = Path("config/contacted_list.json")
SYSTEM_STATE_PATH = Path("config/system_state.json")


def load_contacted_map() -> Dict[str, Dict[str, Any]]:
    if not CONTACTED_PATH.exists():
        return {}
    try:
        return json.loads(CONTACTED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_contacted_map(data: Dict[str, Dict[str, Any]]) -> None:
    CONTACTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTACTED_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert_candidate_status(candidate_id: str, payload: Dict[str, Any]) -> None:
    data = load_contacted_map()
    current = data.get(candidate_id, {})
    current.update(payload)
    data[candidate_id] = current
    save_contacted_map(data)


def load_system_state() -> Dict[str, Any]:
    if not SYSTEM_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SYSTEM_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_system_state(data: Dict[str, Any]) -> None:
    SYSTEM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
