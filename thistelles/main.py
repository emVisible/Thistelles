import os
import queue
import threading

import pyperclip
import rumps
from pynput import keyboard

from . import config as cfg
from . import history as hist
from . import log as log_mod
from . import recorder
from . import transcriber
from . import waveform

logger = log_mod.get_logger()


def notify(title: str, subtitle: str, message: str):
    try:
        from UserNotifications import (
            UNMutableNotificationContent,
            UNNotificationRequest,
            UNTimeIntervalNotificationTrigger,
            UNUserNotificationCenter,
        )

        center = UNUserNotificationCenter.currentNotificationCenter()
        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setSubtitle_(subtitle)
        content.setBody_(message)
        trigger = UNTimeIntervalNotificationTrigger.triggerWithTimeInterval_repeats_(0.1, False)
        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            "voice-input", content, trigger
        )
        center.addNotificationRequest_completionHandler_(request, None)
    except Exception:
        pass


_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _asset_path(name: str) -> str:
    return os.path.join(_ASSETS_DIR, name)



def _play_sound(name: str):
    from AppKit import NSSound

    path = os.path.expanduser(f"~/.voice-input/sounds/{name}.wav")
    if not os.path.exists(path):
        path = _asset_path(f"{name}.wav")
    if not os.path.exists(path):
        path = f"/System/Library/Sounds/{name}.aiff"
        if not os.path.exists(path):
            return
    NSSound.alloc().initWithContentsOfFile_byReference_(path, True).play()


LANGUAGES = [
    ("zh-CN", "中文"),
    ("en-US", "English"),
]

HISTORY_LIMITS = [50, 100, 200]
MODES = ["base", "max"]

UI_STRINGS = {
    "zh-CN": {
        "start": "开始录音",
        "stop": "停止录音",
        "settings": "配置",
        "history": "历史记录",
        "language": "切换语言",
        "mode": "精度模式",
        "base": "标准",
        "max": "高精度",
        "limit": "历史上限",
        "no_history": "暂无记录",
        "clear_history": "清空历史",
        "quit": "退出",
        "notify_title": "语音输入",
        "notify_copied": "已复制到剪贴板",
        "notify_fail": "未识别到语音",
        "notify_retry": "请重试",
        "notify_model_error": "模型加载失败，请重新安装或切换为标准模式",
        "notify_inference_error": "转写出错，请重试",
        "model_downloading": "正在下载 large-v3 模型（约3GB），首次转录会较慢",
        "not_installed": "未下载",
    },
    "en-US": {
        "start": "Start Recording",
        "stop": "Stop Recording",
        "settings": "Settings",
        "history": "History",
        "language": "Language",
        "mode": "Mode",
        "base": "Base",
        "max": "Max",
        "limit": "History Limit",
        "no_history": "No Records",
        "clear_history": "Clear History",
        "quit": "Quit",
        "notify_title": "Thistelles",
        "notify_copied": "Copied to Clipboard",
        "notify_fail": "No Speech Detected",
        "notify_retry": "Please try again",
        "notify_model_error": "Model load failed. Reinstall or switch to Base mode.",
        "notify_inference_error": "Transcription failed. Please retry.",
        "model_downloading": "Downloading large-v3 model (~3GB). First transcription will be slower.",
        "not_installed": "not cached",
    },
}


class VoiceInputApp(rumps.App):
    def __init__(self):
        self._toggling = False

        self._config = cfg.load()
        logger.info("config loaded: language=%s mode=%s hotkey=%s",
                     self._config.get("language"),
                     self._config.get("mode"),
                     self._config.get("hotkey"))

        self._icon_idle = _asset_path("mic_idle.png")
        self._icon_rec = _asset_path("mic_rec.png")
        super().__init__("", icon=self._icon_idle, template=True, quit_button=None)
        self._queue: queue.Queue = queue.Queue()
        self._recorder = recorder.Recorder()
        self._waveform = waveform.WaveformOverlay(self._config)
        self._hotkey_listener: keyboard.GlobalHotKeys | None = None

        self._toggle_item = rumps.MenuItem(self._tr("start"))
        self._toggle_item.set_callback(self._on_toggle_clicked)

        self._quit_item = rumps.MenuItem(self._tr("quit"))
        self._quit_item.set_callback(lambda _: rumps.quit_application())

        self._history_menu = rumps.MenuItem(self._tr("history"))
        self._language_menu = rumps.MenuItem(self._tr("language"))
        self._lang_items: dict[str, rumps.MenuItem] = {}
        self._mode_menu = rumps.MenuItem(self._tr("mode"))
        self._mode_items: dict[str, rumps.MenuItem] = {}
        self._limit_menu = rumps.MenuItem(self._tr("limit"))
        self._limit_items: dict[int, rumps.MenuItem] = {}

        self._settings_menu = rumps.MenuItem(self._tr("settings"))
        self._settings_menu.add(self._mode_menu)
        self._settings_menu.add(self._language_menu)
        self._settings_menu.add(self._limit_menu)

        self.menu = [
            self._toggle_item,
            None,
            self._history_menu,
            self._settings_menu,
            None,
            self._quit_item,
        ]

        self._setup_language()
        self._setup_limit()
        self._setup_mode()
        self._refresh_ui()
        self._rebuild_history()
        self._start_hotkey()
        self._timer_amp = None
        self._timer = rumps.Timer(self._poll_queue, 0.1)
        self._timer.start()
        logger.info("app: ready")

        threading.Thread(
            target=self._preload_model,
            args=(self._config.get("mode", "base"),),
            daemon=True,
        ).start()

    def _preload_model(self, mode: str):
        transcriber.preload(mode)

    def _tr(self, key: str) -> str:
        lang = self._config.get("language", "zh-CN")
        return UI_STRINGS.get(lang, UI_STRINGS["zh-CN"]).get(key, key)

    # ── hotkey ──────────────────────────────────────────────────────

    @staticmethod
    def _to_pynput_hotkey(hotkey_str: str) -> str:
        parts = hotkey_str.lower().replace("-", "+").split("+")
        result = []
        for p in parts:
            if p in ("cmd", "shift", "ctrl", "alt", "option", "command", "control"):
                result.append(f"<{p}>")
            else:
                result.append(p)
        return "+".join(result)

    def _start_hotkey(self):
        hotkey_str = self._to_pynput_hotkey(self._config["hotkey"])
        logger.info("hotkey: registering %s", self._config["hotkey"])

        def on_activate():
            self._queue.put(("toggle", None))

        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({hotkey_str: on_activate})
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        logger.info("hotkey: ready")

    # ── queue poll (main thread) ────────────────────────────────────

    def _poll_queue(self, _):
        try:
            action, data = self._queue.get_nowait()
        except queue.Empty:
            return

        if action == "toggle":
            self._toggle()

        elif action == "notify_ok":
            _play_sound("stop")
            preview = (data[:60] + "…") if data and len(data) > 60 else (data or "")
            notify(self._tr("notify_title"), self._tr("notify_copied"), preview)
            self._rebuild_history()

        elif action == "notify_fail":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_fail"), self._tr("notify_retry"))

        elif action == "notify_model_error":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_model_error"), "")

        elif action == "notify_inference_error":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_inference_error"), "")

    # ── waveform ───────────────────────────────────────────────────

    def _poll_amplitude(self, _):
        if self._recorder.recording:
            self._waveform.update(self._recorder.latest_amplitude)

    # ── recording toggle ────────────────────────────────────────────

    def _on_toggle_clicked(self, _):
        self._toggle()

    def _toggle(self):
        if self._toggling:
            return
        self._toggling = True
        try:
            if self._recorder.recording:
                self._stop()
            else:
                self._start()
        finally:
            self._toggling = False

    def _start(self):
        logger.info("recording: start")
        self._waveform.show()
        self._recorder.start()
        self._timer_amp = rumps.Timer(self._poll_amplitude, 0.03)
        self._timer_amp.start()
        self.icon = self._icon_rec
        self._toggle_item.title = self._tr("stop")
        _play_sound("start")

    def _stop(self):
        logger.info("recording: stop")
        if self._timer_amp:
            self._timer_amp.stop()
            self._timer_amp = None
        self._waveform.hide()
        self.icon = self._icon_idle
        self._toggle_item.title = self._tr("start")

        wav_path = self._recorder.stop()
        if not wav_path:
            notify(self._tr("notify_title"), self._tr("notify_fail"), self._tr("notify_retry"))
            return

        threading.Thread(
            target=self._transcribe_async, args=(wav_path,), daemon=True
        ).start()

    def _transcribe_async(self, wav_path: str):
        lang = self._config["language"]
        mode = self._config.get("mode", "base")
        logger.info("transcribe: starting mode=%s lang=%s", mode, lang)
        text, err = transcriber.transcribe(
            wav_path,
            lang,
            mode,
            5,
        )
        try:
            os.unlink(wav_path)
        except Exception:
            pass
        if err == "model_error":
            logger.error("transcribe: model error")
            self._queue.put(("notify_model_error", None))
            return
        if err == "inference_error":
            logger.error("transcribe: inference error")
            self._queue.put(("notify_inference_error", None))
            return
        if not text:
            logger.warning("transcribe: no speech detected")
            self._queue.put(("notify_fail", None))
            return
        pyperclip.copy(text)
        hist.add(text, self._config["history_limit"])
        logger.info("transcribe: done (%d chars) %s", len(text), text[:60])
        self._queue.put(("notify_ok", text))

    # ── history ─────────────────────────────────────────────────────

    def _rebuild_history(self):
        if self._history_menu._menu:
            self._history_menu.clear()
        entries = hist.load()
        if not entries:
            self._history_menu.add(rumps.MenuItem(self._tr("no_history")))
            return
        for e in entries[:15]:
            label = f"{e['time']}  {e['text'][:28]}"
            item = rumps.MenuItem(label)
            t = e["text"]
            item.set_callback(lambda _, text=t: pyperclip.copy(text))
            self._history_menu.add(item)
        self._history_menu.add(None)
        clear_item = rumps.MenuItem(self._tr("clear_history"))
        clear_item.set_callback(self._on_clear_history)
        self._history_menu.add(clear_item)

    def _on_clear_history(self, _):
        hist.clear()
        self._rebuild_history()

    # ── language ────────────────────────────────────────────────────

    def _setup_language(self):
        self._lang_items.clear()
        for key, label in LANGUAGES:
            item = rumps.MenuItem(label)
            item.set_callback(lambda _, k=key: self._set_language(k))
            self._language_menu.add(item)
            self._lang_items[key] = item
        self._refresh_language_state()

    def _refresh_language_state(self):
        current = self._config["language"]
        for key, item in self._lang_items.items():
            item.state = key == current

    def _set_language(self, key: str):
        logger.info("language: %s -> %s", self._config["language"], key)
        self._config["language"] = key
        cfg.save(self._config)
        self._refresh_language_state()
        self._refresh_ui()
        self._rebuild_history()

    # ── history limit ───────────────────────────────────────────────

    def _setup_limit(self):
        self._limit_items.clear()
        for v in HISTORY_LIMITS:
            item = rumps.MenuItem(str(v))
            item.set_callback(lambda _, limit=v: self._set_limit(limit))
            self._limit_menu.add(item)
            self._limit_items[v] = item
        self._refresh_limit_state()

    def _refresh_limit_state(self):
        current = self._config["history_limit"]
        for v, item in self._limit_items.items():
            item.state = v == current

    def _set_limit(self, limit: int):
        self._config["history_limit"] = limit
        cfg.save(self._config)
        self._refresh_limit_state()

    # ── mode ────────────────────────────────────────────────────────

    def _setup_mode(self):
        self._mode_items.clear()
        max_cached = transcriber.max_available()
        for m in MODES:
            label = self._tr(m)
            if m == "max" and not max_cached:
                label += f" ({self._tr('not_installed')})"
            item = rumps.MenuItem(label)
            item.set_callback(lambda _, mode=m: self._set_mode(mode))
            self._mode_menu.add(item)
            self._mode_items[m] = item
        self._refresh_mode_state()

    def _refresh_mode_state(self):
        current = self._config.get("mode", "base")
        for m, item in self._mode_items.items():
            item.state = m == current

    def _set_mode(self, mode: str):
        logger.info("mode: %s -> %s", self._config.get("mode"), mode)
        self._config["mode"] = mode
        cfg.save(self._config)
        self._refresh_mode_state()

    # ── UI refresh ──────────────────────────────────────────────────

    def _refresh_ui(self):
        self._toggle_item.title = self._tr("stop") if self._recorder.recording else self._tr("start")
        self._settings_menu.title = self._tr("settings")
        self._history_menu.title = self._tr("history")
        self._language_menu.title = self._tr("language")
        self._mode_menu.title = self._tr("mode")
        self._limit_menu.title = self._tr("limit")
        self._quit_item.title = self._tr("quit")
        self._refresh_language_state()
        self._refresh_mode_state()

    # ── cleanup ─────────────────────────────────────────────────────

    def _cleanup(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self._waveform.hide()


def main():
    import importlib.metadata
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        try:
            print(f"thistelles {importlib.metadata.version('thistelles')}")
        except Exception:
            print("thistelles")
        return
    app = VoiceInputApp()
    try:
        app.run()
    finally:
        app._cleanup()


if __name__ == "__main__":
    main()
