"""原生设置窗口：AppKit 程序化布局，所有改动即时生效。

架构约束：

- 本模块只做「控件 ↔ 配置读写 + 应用层副作用」的桥接；
  业务规则仍归属各自模块（层间职责分离）
- 所有配置变更统一经 app.apply_config(key, value) 路由——
  该方法是应用侧副作用与持久化的单一真相源
- 快捷键捕获使用 NSEvent 本地监听（窗口聚焦期），无需辅助功能权限，
  且捕获期间挂起全局热键，避免组合键误触发录音切换
"""

import logging
import objc
import webbrowser
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSEvent,
    NSEventMaskKeyDown,
    NSFont,
    NSMakeRect,
    NSPopUpButton,
    NSRadioButton,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSMakePoint

from . import config as cfg
from . import recorder
from . import vocab
from .keymap import (
    base_character,
    canonical_hotkey,
    is_cancel_keycode,
    modifiers_from_flags,
    symbol_for,
)

logger = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/emVisible/Thistelles"

WINDOW_SIZE = (480, 640)

POPUP_DEFS = {
    "output_mode": [
        ("插入光标处", "paste"),
        ("插入并保留剪贴板", "both"),
        ("仅复制剪贴板", "clipboard"),
    ],
    "language": [
        ("自动检测", "auto"),
        ("中文", "zh-CN"),
        ("English", "en-US"),
        ("日本語", "ja"),
        ("한국어", "ko"),
        ("Deutsch", "de"),
        ("Français", "fr"),
        ("Español", "es"),
        ("Русский", "ru"),
        ("Português", "pt"),
    ],
    "model_variant": [("fp16（默认）", "fp16"), ("q4（省内存）", "q4")],
    "history_limit": [("50", 50), ("100", 100), ("200", 200)],
    "auto_stop_silence_s": [("关闭", 0), ("2 秒", 2), ("3 秒", 3), ("5 秒", 5)],
    "max_record_s": [("5 分钟", 300), ("10 分钟", 600), ("20 分钟", 1200)],
    "model_idle_unload_min": [
        ("常驻", 0),
        ("10 分钟", 10),
        ("30 分钟", 30),
        ("60 分钟", 60),
    ],
}


def _label(text):
    tf = NSTextField.labelWithString_(text)
    f = tf.frame()
    tf.setFrame_(((24, 0), (112, f.size.height)))
    return tf


class SettingsPanel(NSObject):
    """设置面板控制器：持有窗口与全部控件引用。"""

    def initWithApp_(self, app):
        self = objc.super(SettingsPanel, self).init()
        if not self:
            return None
        self.app = app
        self.window = None
        self.hotkeyField = None
        self.rerecordBtn = None
        self.popups = {}        # config_key -> NSPopUpButton
        self.popupValues = {}   # config_key -> [values]
        self.modeBase = None
        self.modeMax = None
        self.variantFp16 = None
        self.variantQ4 = None
        self.keyToggle = None
        self.keyPtt = None
        self.capturing = False
        self.monitor = None
        return self

    # ── 对外入口 ─────────────────────────────────────────────────

    def show(self):
        if self.window is not None:
            self.window.makeKeyAndOrderFront_(None)
            self._activate_app()
            return
        self.window = self._build_window()
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self._activate_app()

    def _activate_app(self):
        try:
            app = NSApplication.sharedApplication()
            app.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    # ── 布局构建 ─────────────────────────────────────────────────

    def _build_window(self):
        w, h = WINDOW_SIZE
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((120, 120), (w, h)),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("Thistelles 设置")
        win.setBackgroundColor_(NSColor.windowBackgroundColor())

        content = NSView.alloc().initWithFrame_(((0, 0), (w, h)))
        win.setContentView_(content)

        state = {"y": h - 52}

        def label_row(text):
            lb = _label(text)
            lb.setFrameOrigin_(NSMakePoint(24, state["y"] + 7))
            content.addSubview_(lb)

        def control_at(control):
            control.setFrameOrigin_(NSMakePoint(140, state["y"]))
            content.addSubview_(control)

        def advance(step=36):
            state["y"] -= step

        def gap(step=14):
            state["y"] -= step

        def add_popup(key):
            label_row(cfg_label_for(key))
            p = self._make_popup(((140, state["y"]), (310, 26)), key)
            content.addSubview_(p)
            advance()

        def add_radio_pair(label_text, left_title, left_value, right_title,
                           right_value, current, action):
            label_row(label_text)
            b1 = NSButton.alloc().initWithFrame_(NSMakeRect(140, state["y"], 130, 24))
            b1.setButtonType_(NSRadioButton)
            b1.setTitle_(left_title)
            b1.setTarget_(self)
            b1.setAction_(action)
            b1.setValue_(left_value)
            content.addSubview_(b1)
            b2 = NSButton.alloc().initWithFrame_(NSMakeRect(282, state["y"], 160, 24))
            b2.setButtonType_(NSRadioButton)
            b2.setTitle_(right_title)
            b2.setTarget_(self)
            b2.setAction_(action)
            b2.setValue_(right_value)
            content.addSubview_(b2)
            if str(current) == str(left_value):
                b1.setState_(1)
            elif str(current) == str(right_value):
                b2.setState_(1)
            advance()

        # ── 录音快捷键 ──
        label_row("录音快捷键")
        self.hotkeyField = NSTextField.textFieldWithString_(
            symbol_for(str(self.app.config_get("hotkey", "")))
        )
        self.hotkeyField.setFrame_(NSMakeRect(140, state["y"], 168, 26))
        self.hotkeyField.setEditable_(False)
        self.hotkeyField.setBordered_(True)
        self.hotkeyField.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0.5))
        content.addSubview_(self.hotkeyField)
        self.rerecordBtn = NSButton.alloc().initWithFrame_(
            NSMakeRect(318, state["y"], 96, 26)
        )
        self.rerecordBtn.setTitle_("重新录制")
        self.rerecordBtn.setBezelStyle_(1)
        self.rerecordBtn.setTarget_(self)
        self.rerecordBtn.setAction_("startCapture:")
        content.addSubview_(self.rerecordBtn)
        advance()

        # ── 输出与语言 ──
        add_popup("output_mode")
        add_popup("language")
        gap()

        # ── 引擎相关 ──
        cur_mode = str(self.app.config_get("mode", "base"))
        cur_variant = str(self.app.config_get("model_variant", "fp16"))
        label_row("精度模式")
        self.modeBase = self._radio("标准 base", left=True)
        self.modeBase.setValue_("base")
        content.addSubview_(self.modeBase)
        self.modeMax = self._radio("高精度 turbo", left=False)
        self.modeMax.setValue_("max")
        content.addSubview_(self.modeMax)
        if cur_mode == "base":
            self.modeBase.setState_(1)
        else:
            self.modeMax.setState_(1)
        advance()

        label_row("模型量化")
        self.variantFp16 = self._radio("fp16", left=True)
        self.variantFp16.setValue_("fp16")
        content.addSubview_(self.variantFp16)
        self.variantQ4 = self._radio("q4 省内存", left=False)
        self.variantQ4.setValue_("q4")
        content.addSubview_(self.variantQ4)
        if cur_variant == "fp16":
            self.variantFp16.setState_(1)
        else:
            self.variantQ4.setState_(1)
        advance()

        add_popup("model_idle_unload_min")
        gap()

        # ── 录音行为 ──
        cur_hm = str(self.app.config_get("hotkey_mode", "toggle"))
        label_row("按键模式")
        self.keyToggle = self._radio("点击切换", left=True)
        self.keyToggle.setValue_("toggle")
        content.addSubview_(self.keyToggle)
        self.keyPtt = self._radio("按住说话", left=False)
        self.keyPtt.setValue_("ptt")
        content.addSubview_(self.keyPtt)
        if cur_hm == "toggle":
            self.keyToggle.setState_(1)
        else:
            self.keyPtt.setState_(1)
        advance()

        add_popup("__mic__")
        add_popup("auto_stop_silence_s")
        add_popup("max_record_s")
        gap()

        # ── 历史 ──
        add_popup("history_limit")
        gap()

        # ── 底部链接行 ──
        link_y = 22
        bx = 20
        for title, sel in (
            ("编辑热词", "openHotwords:"),
            ("纠正词典", "openCorrections:"),
            ("数据目录", "openDataDir:"),
            ("⭐ GitHub", "openGitHub:"),
        ):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(bx, link_y, 104, 26))
            b.setTitle_(title)
            b.setBezelStyle_(1)
            b.setTarget_(self)
            b.setAction_(sel)
            content.addSubview_(b)
            bx += 112

        # 版本角标
        ver = NSTextField.labelWithString_(f"v{self.app.version_string()}")
        vf = ver.frame()
        ver.setFrameOrigin_(NSMakePoint(w - vf.size.width - 16, link_y + 6))
        ver.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(ver)

        return win

    def _radio(self, title, left):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 150, 24))
        b.setButtonType_(NSRadioButton)
        b.setTitle_(title)
        b.setTarget_(self)
        b.setAction_("precisionChanged:" if left else "variantChanged:")
        return b

    def _make_popup(self, frame, key):
        p = NSPopUpButton.alloc().initWithFrame_pullsDown_(frame, False)

        if key == "__mic__":
            p.addItemWithTitle_("系统默认")
            for dev in recorder.Recorder.enumerate_inputs()[:12]:
                name = dev["name"] or f"device #{dev['index']}"
                if len(name) > 34:
                    name = name[:32] + "…"
                p.addItemWithTitle_(name)
            current = str(self.app.config_get("input_device_name", "")).strip().lower()
            names = [""] + [
                d["name"].lower()[:32]
                for d in recorder.Recorder.enumerate_inputs()[:12]
            ]
            idx = next((i for i, n in enumerate(names) if n == current), 0)
            p.selectItemAtIndex_(idx)
            p.setTarget_(self)
            p.setAction_("micChanged:")
            return p

        defs = POPUP_DEFS[key]
        labels = [t for t, _v in defs]
        values = [v for _t, v in defs]
        for t in labels:
            p.addItemWithTitle_(t)
        current = str(self.app.config_get(key, ""))
        for i, v in enumerate(values):
            if str(v) == current:
                p.selectItemAtIndex_(i)
                break
        p.setTarget_(self)
        p.setAction_("popupChanged:")
        self.popups[key] = p
        self.popupValues[key] = values
        return p

    # ── 事件路由 ─────────────────────────────────────────────────

    def popupChanged_(self, sender):
        for key, btn in self.popups.items():
            if btn == sender:
                idx = int(sender.indexOfSelectedItem())
                value = self.popup_values[key][idx]
                self.app.apply_config(key, value)
                return

    def micChanged_(self, sender):
        idx = int(sender.indexOfSelectedItem())
        if idx == 0:
            self.app.apply_config("input_device_name", "")
            return
        devices = recorder.Recorder.enumerate_inputs()[:12]
        if 1 <= idx <= len(devices):
            self.app.apply_config("input_device_name", devices[idx - 1]["name"])

    def precisionChanged_(self, sender):
        value = "max" if sender == self.modeMax else "base"
        self.app.apply_config("mode", value)

    def variantChanged_(self, sender):
        value = "q4" if sender == self.variantQ4 else "fp16"
        self.app.apply_config("model_variant", value)

    def keyModeChanged_(self, sender):
        value = "ptt" if sender == self.keyPtt else "toggle"
        self.app.apply_config("hotkey_mode", value)

    # ── 快捷键捕获 ───────────────────────────────────────────────

    def startCapture_(self, sender):
        if self.capturing:
            self._end_capture(cancel=True)
            return
        self.capturing = True
        self.rerecordBtn.setTitle_("按下组合键… Esc 取消")
        self.hotkeyField.setStringValue_("…")
        self.app.suspend_global_hotkeys()
        self.monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, self.captureHandler_
        )

    def captureHandler_(self, event):
        if not self.capturing:
            return event

        if keymap.is_cancel_keycode(int(event.keyCode())):
            self._end_capture(cancel=True)
            return None

        mods = keymap.modifiers_from_flags(int(event.modifierFlags()))
        ch = keymap.base_character(event)
        if not mods or not ch:
            return None  # 必须携带至少一个修饰键；吞掉无效按键

        hk = keymap.canonical_hotkey(mods, ch)
        self.hotkeyField.setStringValue_(symbol_for(hk))
        self.app.apply_config("hotkey", hk)

        self._end_capture(cancel=False)
        return None  # 吞掉本次按键事件

    def _end_capture(self, cancel=False):
        if self.monitor is not None:
            try:
                NSEvent.removeMonitor_(self.monitor)
            except Exception:
                pass
            self.monitor = None
        self.capturing = False
        self.rerecordBtn.setTitle_("重新录制")
        if cancel:
            self.hotkeyField.setStringValue_(
                symbol_for(str(self.app.config_get("hotkey", "")))
            )
            self.app.resume_global_hotkeys()

    # ── 底部链接 ─────────────────────────────────────────────────

    def openHotwords_(self, sender):
        vocab.reveal_hotwords()

    def openCorrections_(self, sender):
        vocab.reveal_corrections()

    def openDataDir_(self, sender):
        import subprocess

        subprocess.Popen(["open", "-R", vocab.DATA_DIR])

    def openGitHub_(self, sender):
        webbrowser.open(GITHUB_URL)


def cfg_label_for(key):
    labels = {
        "output_mode": "输出方式",
        "language": "识别语言",
        "model_variant": "模型量化",
        "history_limit": "历史上限",
        "auto_stop_silence_s": "静音自停",
        "max_record_s": "单次上限",
        "model_idle_unload_min": "闲置卸载",
    }
    return labels.get(key, key)


def show_settings(app) -> SettingsPanel:
    """对外入口：创建或聚焦设置窗口。"""
    panel = getattr(app, "_settings_panel", None)
    if panel is None:
        panel = SettingsPanel.alloc().initWithApp_(app)
        app._settings_panel = panel
    panel.show()
    return panel
