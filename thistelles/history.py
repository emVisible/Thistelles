import json
import os
from datetime import datetime

DATA_DIR = os.path.expanduser("~/.voice-input")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def add(text: str, history_limit: int = 100):
    _ensure_dir()
    entries = load()
    entries.insert(
        0,
        {
            "text": text,
            "time": datetime.now().strftime("%m-%d %H:%M"),
        },
    )
    entries = entries[:history_limit]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def load() -> list[dict]:
    _ensure_dir()
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def clear():
    _ensure_dir()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
