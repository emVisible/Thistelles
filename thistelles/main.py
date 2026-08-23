import os
import queue
import threading
import time

import pyperclip
import rumps

from . import config as cfg
from . import history as hist
from . import hotkeys
from . import inserter as ins
from . import log as log_mod
from . import notifications as notif
from . import recorder
from . import transcriber
from . import vocab
from . import waveform

logger = log_mod.get_logger()


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("thistelles")
    except Exception:
        return "?"


def _build_stamp() -> str:
    """核心模块 mtime 指纹：日志里一眼识别「跑的是不是新代码」。"""
    try:
        import hashlib

        h = hashlib.sha1()
        base = os.path.dirname(__file__)
        for name in ("main.py", "hotkeys.py", "settings_window.py", "vocab.py"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                h.update(name.encode())
                h.update(str(int(os.path.getmtime(p))).encode())
        return h.hexdigest()[:8]
    except Exception:
        return "?"


def _mic_permission() -> str:
    """返回 granted / not_determined / denied / restricted / unknown。"""
    try:
        from AVFoundation import AVMediaTypeAudio, AVCaptureDevice

        status = int(
            AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        )
        return {
            0: "not_determined",
            1: "authorized",
            2: "denied",
            3: "restricted",
        }.get(status, "unknown")
    except Exception:
        return "unknown"


def notify(title: str, subtitle: str, message: str):
    notif.post(title, subtitle, message)


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



HISTORY_LIMITS = [50, 100, 200]
MODES = ["base", "max"]

UI_STRINGS = {
    "zh-CN": {
        "start": "开始录音",
        "stop": "停止录音",
        "transcribing_cancel": "转写中… 点击取消",
        "history": "历史记录",
        "history_search": "搜索历史…",
        "history_pin": "📌 序号置顶/取消…",
        "history_export": "导出历史…",
        "history_clear_search": "✕ 显示全部",
        "history_no_match": "无匹配结果",
        "dlg_ok": "确定",
        "dlg_cancel": "取消",
        "dlg_search_prompt": "输入关键词过滤历史记录：",
        "dlg_pin_prompt": "输入列表序号，置顶/取消置顶该条：",
        "notify_pinned": "已置顶",
        "notify_unpinned": "已取消置顶",
        "notify_export_done": "已导出 {} 条",
        "notify_invalid_index": "无效序号",
        "perm_check_title": "权限提示",
        "perm_missing_ax": "辅助功能权限未授权，全局快捷键不可用。系统设置 → 隐私与安全性 → 辅助功能",
        "perm_missing_mic": "麦克风权限被拒绝，无法录音。系统设置 → 隐私与安全性 → 麦克风",
        "language": "切换语言",
        "mode": "精度模式",
        "base": "标准",
        "max": "高精度",
        "limit": "历史上限",
        "output": "输出方式",
        "out_paste": "插入光标处",
        "out_both": "插入并保留剪贴板",
        "out_clipboard": "仅复制剪贴板",
        "keymode": "按键模式",
        "km_toggle": "点击切换",
        "km_ptt": "按住说话",
        "no_history": "暂无记录",
        "clear_history": "清空历史",
        "quit": "退出",
        "settings_open": "设置",
        "transcribing_cancel": "转写中… 点击取消",
        "notify_title": "语音输入",
        "notify_busy": "上一段还在转写中，请稍候",
        "notify_copied": "已复制到剪贴板",
        "notify_pasted": "已插入到光标处",
        "notify_fail": "未识别到语音",
        "notify_cancelled": "已取消",
        "notify_retry": "请重试",
        "notify_model_error": "模型加载失败，请重新安装或切换为标准模式",
        "notify_inference_error": "转写出错，请重试",
    },
    "en-US": {
        "start": "Start Recording",
        "stop": "Stop Recording",
        "transcribing_cancel": "Transcribing… Click to Cancel",
        "history": "History",
        "history_search": "Search History…",
        "history_pin": "📌 Pin/Unpin by #…",
        "history_export": "Export History…",
        "history_clear_search": "✕ Show All",
        "history_no_match": "No Matches",
        "dlg_ok": "OK",
        "dlg_cancel": "Cancel",
        "dlg_search_prompt": "Keyword to filter history:",
        "dlg_pin_prompt": "Entry number from the list above to pin/unpin:",
        "notify_pinned": "Pinned",
        "notify_unpinned": "Unpinned",
        "notify_export_done": "Exported {} entries",
        "notify_invalid_index": "Invalid number",
        "perm_check_title": "Permissions",
        "perm_missing_ax": "Accessibility permission missing — hotkeys disabled. System Settings → Privacy & Security → Accessibility",
        "perm_missing_mic": "Microphone permission denied — recording unavailable. System Settings → Privacy & Security → Microphone",
        "language": "Language",
        "mode": "Mode",
        "base": "Base",
        "max": "Max",
        "limit": "History Limit",
        "output": "Output Mode",
        "out_paste": "Insert at Cursor",
        "out_both": "Insert & Keep Clipboard",
        "out_clipboard": "Copy Only",
        "keymode": "Key Mode",
        "km_toggle": "Click Toggle",
        "km_ptt": "Hold to Talk",
        "no_history": "No Records",
        "clear_history": "Clear History",
        "quit": "Quit",
        "settings_open": "Settings",
        "transcribing_cancel": "Transcribing… Click to Cancel",
        "notify_title": "Thistelles",
        "notify_busy": "Still transcribing previous clip, please wait",
        "notify_copied": "Copied to Clipboard",
        "notify_pasted": "Inserted at Cursor",
        "notify_fail": "No Speech Detected",
        "notify_cancelled": "Cancelled",
        "notify_retry": "Please try again",
        "notify_model_error": "Model load failed. Reinstall or switch to Base mode.",
        "notify_inference_error": "Transcription failed. Please retry.",
    },
}


class VoiceInputApp(rumps.App):
    def __init__(self):
        self._toggling = False
        self._transcribing = False
        self._last_text = ""
        self._cancel_event: threading.Event | None = None
        self._silence_since: float | None = None
        self._sleep_assertion = None
        self._notify_auth_timer = None
        self._hotkey_resume_timer = None

        self._config = cfg.load()
        logger.info(
            "config loaded: language=%s mode=%s hotkey=%s build=%s",
            self._config.get("language"),
            self._config.get("mode"),
            self._config.get("hotkey"),
            _build_stamp(),
        )

        self._icon_idle = _asset_path("mic_idle.png")
        self._icon_rec = _asset_path("mic_rec.png")
        transcriber.set_variant(self._config.get("model_variant", "fp16"))
        super().__init__("", icon=self._icon_idle, template=True, quit_button=None)
        self._queue: queue.Queue = queue.Queue()
        self._recorder = recorder.Recorder()
        self._waveform = waveform.WaveformOverlay(self._config)
        self._hotkey_listener = None
        self._hotkeys_suspended = False
        self._hotkey_retry_timer: threading.Timer | None = None

        self._toggle_item = rumps.MenuItem(self._tr("start"))
        self._toggle_item.set_callback(self._on_toggle_clicked)

        self._quit_item = rumps.MenuItem(self._tr("quit"))
        self._quit_item.set_callback(lambda _: rumps.quit_application())

        self._history_menu = rumps.MenuItem(self._tr("history"))
        self._history_query: str | None = None
        self._history_rows: list[dict] = []
        self._history_search_item = rumps.MenuItem(self._tr("history_search"))
        self._history_search_item.set_callback(self._on_history_search)
        self._history_pin_item = rumps.MenuItem(self._tr("history_pin"))
        self._history_pin_item.set_callback(self._on_history_pin_dialog)
        self._history_export_item = rumps.MenuItem(self._tr("history_export"))
        self._history_export_item.set_callback(self._on_history_export)
        self._dialog_pending = False

        self._settings_item = rumps.MenuItem(self._tr("settings_open"))
        self._settings_item.set_callback(lambda _: self.open_settings())

        self.menu = [
            self._toggle_item,
            None,
            self._history_menu,
            self._settings_item,
            None,
            self._quit_item,
        ]

        self._refresh_ui()
        self._rebuild_history()
        self._timer_amp = None
        vocab.ensure_correction_file()
        t = threading.Timer(1.0, self._sync_hotkey)
        t.daemon = True
        t.start()
        self._check_permissions_async()
        self._timer = rumps.Timer(self._poll_queue, 0.1)
        self._timer.start()
        self._notify_auth_timer = threading.Timer(
            2.0, notif.ensure_authorization
        )
        self._notify_auth_timer.daemon = True
        self._notify_auth_timer.start()
        logger.info("app: ready")

        threading.Thread(
            target=self._preload_model,
            args=(
                self._config.get("mode", "base"),
                float(self._config.get("model_idle_unload_min", 30) or 0),
            ),
            daemon=True,
        ).start()

    def _preload_model(self, mode: str, idle_unload_min: float = 0.0):
        transcriber.preload(mode, idle_unload_min)

    # ── 对外公共接口（设置窗口 / 菜单共用）────────────────────

    def config_get(self, key, default=None):
        return self._config.get(key, default)

    def version_string(self) -> str:
        return _app_version()

    def apply_config(self, key, value):
        """配置变更统一路由：持久化 + 触发对应副作用（单一真相源）。

        注意顺序：先改内存再持久化，最后触发副作用——
        副作用（如重挂热键、预载模型）读取的必须是新值。
        """
        logger.info("apply_config: %s = %r", key, value)
        self._config[key] = value

        if key == "hotkey":
            cfg.save(self._config)
            self._sync_hotkey()
        elif key == "model_variant":
            cfg.save(self._config)
            transcriber.set_variant(value)
        elif key == "input_device_name":
            cfg.save(self._config)
            self._recorder.set_device_by_name(str(value))
        elif key == "hotkey_mode":
            cfg.save(self._config)
            self._sync_hotkey()
        elif key == "mode":
            cfg.save(self._config)
            threading.Thread(
                target=self._preload_model,
                args=(
                    str(value),
                    float(self._config.get("model_idle_unload_min", 30) or 0),
                ),
                daemon=True,
            ).start()
        elif key == "language":
            cfg.save(self._config)
        elif key == "ui_language":
            cfg.save(self._config)
            self._refresh_ui()  # 菜单文案即时切换
        elif key == "model_idle_unload_min":
            cfg.save(self._config)
            # 立即按新值重排闲置卸载定时器，而非等下次转写
            transcriber.apply_idle_unload(float(value or 0))
        else:
            # output_mode / history_limit / auto_stop_silence_s /
            # max_record_s / model_idle_unload_min 等在各自消费点直读配置
            cfg.save(self._config)

    def suspend_global_hotkeys(self):
        """快捷键捕获期间挂起全局监听，避免组合键误触发录音。"""
        self._hotkeys_suspended = True
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    def resume_global_hotkeys(self):
        self._hotkeys_suspended = False
        self._hotkey_resume_timer = threading.Timer(0.2, self._sync_hotkey)
        self._hotkey_resume_timer.daemon = True
        self._hotkey_resume_timer.start()

    def open_settings(self):
        from . import settings_window

        settings_window.show_settings(self)

    def _tr(self, key: str) -> str:
        # 界面显示语言（ui_language）与识别语言（language）相互独立
        lang = self._config.get("ui_language", "zh-CN")
        return UI_STRINGS.get(lang, UI_STRINGS["zh-CN"]).get(key, key)

    # ── hotkey（Quartz CGEventTap 常驻实例，配置变化原地更新）──────

    def _sync_hotkey(self):
        """确保常驻 tap 与当前配置一致；绝不销毁重建端口。

        背景：每次改设置都重建 event tap，系统会逐渐拒绝
        CGEventTapCreate（Mach 端口耗尽/TCC 复查），快捷键随之永久失效。
        """
        hotkey_str = str(self._config.get("hotkey", ""))
        logger.info("hotkey: syncing %s (mode=%s)",
                    hotkey_str, self._config.get("hotkey_mode", "toggle"))

        def on_press():
            mode = self._config.get("hotkey_mode", "toggle")
            self._queue.put(("ptt_down" if mode == "ptt" else "toggle", None))

        def on_release():
            # 生产端即按模式分流；消费端另有门禁兜底
            if self._config.get("hotkey_mode") == "ptt":
                self._queue.put(("ptt_up", None))

        try:
            if self._hotkey_listener is None:
                tap = hotkeys.HotkeyTap(hotkey_str, on_press, on_release)
                if not tap.start():
                    logger.error(
                        "hotkey: failed to register (accessibility?) — "
                        "系统设置→隐私与安全性→辅助功能 需勾选本应用"
                    )
                    self._schedule_hotkey_retry()  # 授权后自动自愈，无需重启
                    return
                self._hotkey_listener = tap
                logger.info("hotkey: ready (%s)", hotkey_str)
            else:
                self._hotkey_listener.update_hotkey(hotkey_str)
                logger.info("hotkey: updated (%s)", hotkey_str)
        except ValueError:
            logger.exception("hotkey: invalid config, falling back to default")
            self._config["hotkey"] = cfg.DEFAULTS["hotkey"]
            self._sync_hotkey()

    def _schedule_hotkey_retry(self):
        """辅助功能授权通常晚于首次启动完成：周期性重试注册直至成功。

        失败路径仅一次 CGEventTapCreate 调用，开销可忽略；
        捕获挂起期间不重试，避免与捕获 tap 抢事件。
        """
        if self._hotkeys_suspended or self._hotkey_retry_timer is not None:
            return
        t = threading.Timer(8.0, self._retry_hotkey_wakeup)
        t.daemon = True
        t.start()
        self._hotkey_retry_timer = t

    def _retry_hotkey_wakeup(self):
        self._hotkey_retry_timer = None
        if self._hotkey_listener is None and not self._hotkeys_suspended:
            self._sync_hotkey()

    # ── 主按钮三态（开始 / 停止 / 取消转写）────────────────────────

    def _refresh_toggle_title(self):
        if self._recorder.recording:
            self._toggle_item.title = self._tr("stop")
        elif self._transcribing:
            self._toggle_item.title = self._tr("transcribing_cancel")
        else:
            self._toggle_item.title = self._tr("start")

    def _request_transcribe_cancel(self):
        if self._transcribing and self._cancel_event:
            logger.info("cancel: transcription requested")
            self._cancel_event.set()

    def _check_permissions_async(self):
        """启动后延迟检测权限状态，缺失时经队列提醒一次。"""

        def worker():
            problem = None
            try:
                if not ins.accessibility_trusted(prompt=False):
                    problem = "perm_missing_ax"
                elif _mic_permission() == "denied":
                    problem = "perm_missing_mic"
            except Exception:
                logger.debug("perm: check failed", exc_info=True)
            if problem:
                self._queue.put(("notify_perm", problem))

        threading.Timer(4.0, worker).start()
        # 关键：以系统弹窗方式正式请求一次辅助功能权限——
        # 只有请求过的应用才会被注册进「辅助功能」列表，
        # 否则用户在系统设置里根本找不到本应用
        threading.Timer(
            3.0, lambda: self._queue.put(("ax_prompt", None))
        ).start()

    # ── 自定义词典 ──────────────────────────────────────────────────

    def _build_prompt(self) -> str | None:
        parts: list[str] = []
        terms = vocab.load_dictionary_terms()
        if terms:
            parts.append(terms)
        if self._config.get("context_prompt", True) and self._last_text:
            parts.append(self._last_text[-80:])
        prompt = " ".join(parts).strip()
        return prompt[:220] or None

    # ── queue poll (main thread) ────────────────────────────────────

    def _poll_queue(self, _):
        try:
            action, data = self._queue.get_nowait()
        except queue.Empty:
            return

        if action == "toggle":
            self._toggle()

        elif action == "ptt_down":
            # 模式门禁：非 ptt 配置下一律忽略，杜绝残留事件污染 toggle 行为
            if self._config.get("hotkey_mode") != "ptt":
                return
            if self._transcribing:
                notify(self._tr("notify_title"), self._tr("notify_busy"), "")
            elif not self._recorder.recording:
                self._start()

        elif action == "ptt_up":
            if self._config.get("hotkey_mode") != "ptt":
                return
            if self._recorder.recording:
                self._stop()

        elif action == "auto_stop":
            if self._recorder.recording:
                logger.info("recording: auto stop (%s)", data)
                self._stop()

        elif action == "dialog_result":
            payload = data or {}
            value = payload.get("value")
            kind = payload.get("kind")
            self._dialog_pending = False
            if value is None:
                return  # 用户取消
            if kind == "history_search":
                self._history_query = value.strip() or None
                self._rebuild_history()
            elif kind == "history_pin":
                try:
                    idx = int(value.strip().lstrip("#"))
                except ValueError:
                    idx = 0
                # 使用开框时的列表快照，避免等待输入期间列表刷新导致序号错位
                self._apply_pin_index(idx, payload.get("rows") or [])

        elif action == "notify_ok":
            _play_sound("stop")
            preview = (data[:60] + "…") if data and len(data) > 60 else (data or "")
            notify(self._tr("notify_title"), self._tr("notify_copied"), preview)
            if self._history_query:
                self._history_query = None  # 新记录可能不在过滤结果内，避免"消失"
            self._rebuild_history()

        elif action == "notify_pasted":
            _play_sound("stop")
            preview = (data[:60] + "…") if data and len(data) > 60 else (data or "")
            notify(self._tr("notify_title"), self._tr("notify_pasted"), preview)
            if self._history_query:
                self._history_query = None
            self._rebuild_history()

        elif action == "notify_perm":
            notify(
                self._tr("perm_check_title"),
                self._tr(data),
                "",
            )

        elif action == "ax_prompt":
            # 主线程触发系统授权弹窗；已授权时该调用静默无副作用
            try:
                if not ins.accessibility_trusted(prompt=True):
                    logger.warning(
                        "perm: accessibility still untrusted — "
                        "系统设置→隐私与安全性→辅助功能 勾选 Thistelles"
                    )
            except Exception:
                logger.warning("perm: ax prompt failed", exc_info=True)

        elif action == "notify_fail":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_fail"), self._tr("notify_retry"))

        elif action == "notify_model_error":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_model_error"), "")

        elif action == "notify_inference_error":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_inference_error"), "")

        elif action == "transcribe_done":
            self._transcribing = False
            self._cancel_event = None
            self._refresh_toggle_title()

        elif action == "notify_cancelled":
            _play_sound("stop")
            notify(self._tr("notify_title"), self._tr("notify_cancelled"), "")

    # ── waveform ───────────────────────────────────────────────────

    _AUTO_STOP_SILENCE_RMS = 0.02  # recorder 的 RMS 已归一化放大，0.02 ≈ 安静环境底噪

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 60}:{s % 60:02d}"

    def _poll_amplitude(self, _):
        if not self._recorder.recording:
            return
        amp = self._recorder.latest_amplitude
        elapsed = self._recorder.elapsed_seconds
        self._waveform.update(amp, self._format_elapsed(elapsed))

        max_s = int(self._config.get("max_record_s", 600) or 0)
        if max_s > 0 and elapsed >= max_s:
            logger.info("recording: max duration reached (%ds), stopping", max_s)
            self._queue.put(("auto_stop", "max_duration"))
            return

        silence_limit = float(self._config.get("auto_stop_silence_s", 0) or 0)
        if silence_limit > 0:
            now = time.monotonic()
            if amp < self._AUTO_STOP_SILENCE_RMS:
                if self._silence_since is None:
                    self._silence_since = now
                elif now - self._silence_since >= silence_limit:
                    self._silence_since = None
                    logger.info(
                        "recording: silence auto-stop after %.1fs", silence_limit
                    )
                    self._queue.put(("auto_stop", "silence"))
            else:
                self._silence_since = None

    # ── recording toggle ────────────────────────────────────────────

    def _on_toggle_clicked(self, _):
        """主按钮三态：录音中=停止转写；转写中=取消；空闲=开始录音。"""
        if self._toggling:
            return
        if self._recorder.recording:
            self._stop()
        elif self._transcribing:
            self._request_transcribe_cancel()
        else:
            self._toggle()

    def _toggle(self):
        if self._toggling:
            return
        if not self._recorder.recording and self._transcribing:
            notify(self._tr("notify_title"), self._tr("notify_busy"), "")
            return
        self._toggling = True
        try:
            if self._recorder.recording:
                self._stop()
            else:
                self._start()
        finally:
            self._toggling = False

    def _begin_sleep_assertion(self):
        # 录音期间阻止系统空闲休眠（显示器仍可关闭）
        if self._sleep_assertion is not None:
            return
        try:
            from AppKit import NSProcessInfo

            NSIdleSystemSleepDisabled = 1 << 20
            self._sleep_assertion = (
                NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
                    NSIdleSystemSleepDisabled, "Thistelles recording"
                )
            )
        except Exception:
            self._sleep_assertion = None
            logger.debug("sleep assertion: begin failed", exc_info=True)

    def _end_sleep_assertion(self):
        if self._sleep_assertion is None:
            return
        try:
            from AppKit import NSProcessInfo

            NSProcessInfo.processInfo().endActivity_(self._sleep_assertion)
        except Exception:
            logger.debug("sleep assertion: end failed", exc_info=True)
        self._sleep_assertion = None

    def _start(self):
        logger.info("recording: start")
        self._silence_since = None
        self._begin_sleep_assertion()
        self._waveform.show()
        self._recorder.start()
        self._timer_amp = rumps.Timer(self._poll_amplitude, 0.03)
        self._timer_amp.start()
        self.icon = self._icon_rec
        self._refresh_toggle_title()
        _play_sound("start")

    def _stop(self):
        logger.info("recording: stop")
        self._end_sleep_assertion()
        if self._timer_amp:
            self._timer_amp.stop()
            self._timer_amp = None
        self._waveform.hide()
        self.icon = self._icon_idle

        wav_path = self._recorder.stop()
        if not wav_path:
            notify(self._tr("notify_title"), self._tr("notify_fail"), self._tr("notify_retry"))
            return

        self._transcribing = True
        self._cancel_event = threading.Event()
        self._refresh_toggle_title()
        threading.Thread(
            target=self._transcribe_async, args=(wav_path,), daemon=True
        ).start()

    def _transcribe_async(self, wav_path: str):
        lang = self._config["language"]
        mode = self._config.get("mode", "base")
        logger.info("transcribe: starting mode=%s lang=%s", mode, lang)
        try:
            text, err = transcriber.transcribe(
                wav_path,
                lang,
                mode,
                initial_prompt=self._build_prompt(),
                cancel_event=self._cancel_event,
                idle_unload_min=float(
                    self._config.get("model_idle_unload_min", 30) or 0
                ),
            )
            try:
                os.unlink(wav_path)
            except Exception:
                pass
            if err == "cancelled":
                logger.info("transcribe: cancelled")
                self._queue.put(("notify_cancelled", None))
                return
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
            # 确定性纠正层：按 corrections.md 的「错误 → 正确」逐条替换
            text = vocab.apply_corrections(text, vocab.load_correction_pairs())
            hist.add(text, self._config["history_limit"])
            self._last_text = text
            logger.info("transcribe: done (%d chars) %s", len(text), text[:60])
            mode = self._config.get("output_mode", "paste")
            delay = int(self._config.get("paste_delay_ms", 120))
            pasted, eff_mode = ins.deliver(text, mode, delay)
            if eff_mode == "paste":
                self._queue.put(("notify_pasted", text))
            else:
                self._queue.put(("notify_ok", text))
        except Exception:
            logger.exception("transcribe: unexpected error")
            self._queue.put(("notify_inference_error", None))
        finally:
            self._queue.put(("transcribe_done", None))

    # ── history ─────────────────────────────────────────────────────

    def _rebuild_history(self):
        if self._history_menu._menu:
            self._history_menu.clear()

        self._history_menu.add(self._history_search_item)
        self._history_pin_item.title = self._tr("history_pin")
        self._history_menu.add(self._history_pin_item)
        self._history_export_item.title = self._tr("history_export")
        self._history_menu.add(self._history_export_item)

        query = (self._history_query or "").strip().lower()
        rows = hist.ordered()
        if query:
            q_item = rumps.MenuItem(
                self._tr("dlg_search_prompt") + " " + self._history_query
            )
            self._history_menu.add(q_item)
            clear_item = rumps.MenuItem(self._tr("history_clear_search"))
            clear_item.set_callback(lambda _: self._clear_history_search())
            self._history_menu.add(clear_item)
            rows = [e for e in rows if query in e.get("text", "").lower()]
        self._history_rows = rows

        if not rows:
            empty = rumps.MenuItem(
                self._tr("history_no_match") if query else self._tr("no_history")
            )
            self._history_menu.add(empty)
        for i, e in enumerate(rows, 1):
            mark = "📌 " if e.get("pinned") else ""
            label = f"{mark}{i}. {e['time']}  {e['text'][:28]}"
            t = e["text"]
            item = rumps.MenuItem(label)
            item.set_callback(lambda _, text=t: pyperclip.copy(text))
            mi = getattr(item, "_menuitem", None)
            if mi is not None:
                try:
                    mi.setToolTip_(t)  # 悬浮查看完整文本
                except Exception:
                    pass
            self._history_menu.add(item)

        self._history_menu.add(None)
        clear_item = rumps.MenuItem(self._tr("clear_history"))
        clear_item.set_callback(self._on_clear_history)
        self._history_menu.add(clear_item)

    def _clear_history_search(self, _):
        self._history_query = None
        self._rebuild_history()

    @staticmethod
    def _osascript_escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def _prompt_text(self, message: str) -> str | None:
        """模态输入框；返回输入文本，取消返回 None。"""
        import subprocess

        script = (
            'display dialog "{}" default answer "" '
            'buttons {{"{}", "{}"}} default button "{}" with title "Thistelles"'
        ).format(
            self._osascript_escape(message),
            self._tr("dlg_cancel"),
            self._tr("dlg_ok"),
            self._tr("dlg_ok"),
        )
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            return None
        for part in r.stdout.strip().split(","):
            part = part.strip()
            if part.startswith("text returned:"):
                return part[len("text returned:"):]
        return ""

    def _prompt_text_async(self, message: str, kind: str, payload: dict | None = None):
        """后台线程弹出输入框，结果经队列回主线程处理。

        osascript display dialog 会阻塞到用户响应；若在主线程同步等待，
        NSApplication 事件循环停摆导致菜单/快捷键全部假死。
        """
        if self._dialog_pending:
            return

        def worker():
            result = self._prompt_text(message)
            data = {"kind": kind, "value": result}
            if payload:
                data.update(payload)
            self._queue.put(("dialog_result", data))

        self._dialog_pending = True
        threading.Thread(target=worker, daemon=True).start()

    def _on_history_search(self, _):
        self._prompt_text_async(self._tr("dlg_search_prompt"), "history_search")

    def _on_history_pin_dialog(self, _):
        # 快照当前列表：等待输入期间列表可能因新录音刷新；
        # 序号校验在 dialog_result 回调里用快照执行
        snapshot = [dict(e) for e in self._history_rows]
        self._prompt_text_async(
            self._tr("dlg_pin_prompt"), "history_pin", {"rows": snapshot}
        )

    def _apply_pin_index(self, idx: int, rows: list[dict] | None = None):
        rows = self._history_rows if rows is None else rows
        if not 1 <= idx <= len(rows):
            notify(self._tr("notify_title"), self._tr("notify_invalid_index"), "")
            return
        text = rows[idx - 1]["text"]
        state = hist.toggle_pin(text)
        if state is None:
            notify(self._tr("notify_title"), self._tr("notify_invalid_index"), "")
            return
        key = "notify_pinned" if state else "notify_unpinned"
        preview = (text[:60] + "…") if len(text) > 60 else text
        notify(self._tr("notify_title"), self._tr(key), preview)
        self._rebuild_history()

    def _on_history_export(self, _):
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.expanduser(f"~/Downloads/thistelles-history-{ts}.txt")
        try:
            count = hist.export_to(path)
        except Exception:
            logger.exception("history: export failed")
            notify(self._tr("notify_title"), self._tr("notify_fail"), "")
            return
        try:
            import subprocess

            subprocess.Popen(["open", "-R", path])
        except Exception:
            pass
        body = path.replace(os.path.expanduser("~"), "~")
        notify(
            self._tr("notify_title"),
            self._tr("notify_export_done").format(count),
            body,
        )

    def _on_clear_history(self, _):
        hist.clear()
        self._rebuild_history()

    # ── permissions & links ────────────────────────────────────────

    def _refresh_ui(self):
        self._refresh_toggle_title()
        self._settings_item.title = self._tr("settings_open")
        self._history_menu.title = self._tr("history")
        self._history_search_item.title = self._tr("history_search")
        self._history_export_item.title = self._tr("history_export")
        self._quit_item.title = self._tr("quit")

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

    import fcntl
    os.makedirs(os.path.expanduser("~/.voice-input"), exist_ok=True)
    lock_fh = open(os.path.expanduser("~/.voice-input/app.lock"), "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.warning("app: another instance is already running, exiting")
        print("thistelles: another instance is already running", file=sys.stderr)
        return

    try:
        app = VoiceInputApp()
    except Exception:
        logger.exception("app: failed to initialize")
        sys.exit(1)
    try:
        app.run()
    except Exception:
        logger.exception("app: runtime error")
    finally:
        app._cleanup()


if __name__ == "__main__":
    main()
