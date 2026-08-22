import json
import os
from datetime import datetime

DATA_DIR = os.path.expanduser("~/.voice-input")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _save(entries: list[dict]):
    _ensure_dir()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add(text: str, history_limit: int = 100):
    _ensure_dir()
    entries = load()
    entry = {"text": text, "time": datetime.now().strftime("%m-%d %H:%M")}

    # 置顶条目不参与上限裁剪（收藏不被挤掉）；新记录插在置顶区之后。
    pinned = [e for e in entries if e.get("pinned")]
    rest = [e for e in entries if not e.get("pinned")]
    rest.insert(0, entry)
    keep_rest = rest[: max(0, history_limit - len(pinned))]
    _save(pinned + keep_rest)


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
    _save([])


def ordered() -> list[dict]:
    """展示顺序：置顶在前，其余按新到旧。"""
    entries = load()
    return [e for e in entries if e.get("pinned")] + [
        e for e in entries if not e.get("pinned")
    ]


def toggle_pin(text: str) -> bool | None:
    """按文本精确匹配切换置顶；返回切换后的状态，未找到返回 None。

    相同文本的多条记录视为同一收藏项，统一置顶/取消。
    """
    entries = load()
    matches = [e for e in entries if e.get("text") == text]
    if not matches:
        return None
    new_state = not bool(matches[0].get("pinned"))
    for e in matches:
        if new_state:
            e["pinned"] = True
        else:
            e.pop("pinned", None)
    _save(entries)
    return new_state


def export_to(path: str) -> int:
    """导出全部历史（置顶优先）为纯文本；返回条目数。"""
    entries = ordered()
    blocks = []
    for i, e in enumerate(entries, 1):
        mark = " 📌" if e.get("pinned") else ""
        blocks.append(f"{i}. [{e['time']}]{mark}\n{e['text']}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + ("\n" if blocks else ""))
    return len(entries)
