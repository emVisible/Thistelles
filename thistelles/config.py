import json
import os

DATA_DIR = os.path.expanduser("~/.voice-input")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "hotkey": "cmd+shift+'",
    "language": "zh-CN",
    "history_limit": 100,
    "waveform_width": 280,
    "waveform_height": 36,
    "waveform_y": "bottom",
    "mode": "base",
    "output_mode": "paste",
    "paste_delay_ms": 120,
    "hotkey_mode": "toggle",
    "auto_stop_silence_s": 0,
    "max_record_s": 600,
    "model_idle_unload_min": 30,
    "input_device_name": "",
    "model_variant": "fp16",
}

OUTPUT_MODES = ["paste", "both", "clipboard"]
HOTKEY_MODES = ["toggle", "ptt"]
MODEL_VARIANTS = ["fp16", "q4"]

OUTPUT_MODES = ["paste", "both", "clipboard"]
HOTKEY_MODES = ["toggle", "ptt"]


def _sanitize_number(cfg: dict, key: str, default, minimum: float = 0.0):
    # 负值视为无效输入回退默认（钳到 0 可能意外开启"无限制"语义），而非静默钳位。
    try:
        v = float(cfg.get(key, default))
        if v < 0:
            v = float(default)
    except (TypeError, ValueError):
        v = float(default)
    cfg[key] = max(minimum, v)


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
        if cfg.get("output_mode") not in OUTPUT_MODES:
            cfg["output_mode"] = DEFAULTS["output_mode"]
        if cfg.get("hotkey_mode") not in HOTKEY_MODES:
            cfg["hotkey_mode"] = DEFAULTS["hotkey_mode"]
        _sanitize_number(cfg, "auto_stop_silence_s", DEFAULTS["auto_stop_silence_s"])
        _sanitize_number(cfg, "max_record_s", DEFAULTS["max_record_s"])
        _sanitize_number(cfg, "model_idle_unload_min", DEFAULTS["model_idle_unload_min"])
        cfg["auto_stop_silence_s"] = float(cfg["auto_stop_silence_s"])
        cfg["max_record_s"] = int(cfg["max_record_s"])
        cfg["model_idle_unload_min"] = float(cfg["model_idle_unload_min"])
        if cfg.get("model_variant") not in MODEL_VARIANTS:
            cfg["model_variant"] = DEFAULTS["model_variant"]
        return cfg
    except (json.JSONDecodeError, OSError, TypeError):
        return dict(DEFAULTS)


def save(cfg):
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
