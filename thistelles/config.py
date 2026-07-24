import json
import os

DATA_DIR = os.path.expanduser("~/.voice-input")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "hotkey": "cmd+shift+i",
    "language": "zh-CN",
    "history_limit": 100,
    "waveform_width": 280,
    "waveform_height": 36,
    "waveform_y": "bottom",
    "mode": "base",
}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load():
    _ensure_dir()
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        cfg = {**DEFAULTS, **data}
        if cfg.get("mode") not in ("base", "max"):
            cfg["mode"] = DEFAULTS["mode"]
        return cfg
    except (json.JSONDecodeError, OSError, TypeError):
        return dict(DEFAULTS)


def save(cfg):
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
