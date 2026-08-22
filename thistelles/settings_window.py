"""原生设置窗口：AppKit 程序化布局，所有改动即时生效。

架构约束：

- 本模块只做「控件 ↔ 配置读写 + 应用层副作用」的桥接；
  业务规则仍归属各自模块（层间职责分离）
- 所有配置变更统一经 app.apply_config(key, value) 路由——
  该方法是应用侧副作用与持久化的单一真相源
- 快捷键捕获使用 NSEvent 本地监听（窗口聚焦期），无需辅助功能权限，
  且捕获期间挂起全局热键，避免组合键误触发录音切换

PyObjC 注意事项：NSObject 子类上「必需位置参数 > 0 且不以 _ 结尾」的方法
会被当作 ObjC 选择器做原型校验——带参数的纯辅助函数必须放在模块层。
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

WINDOW_SIZE = (480, 660)

# 弹出菜单定义：config_key -> [(显示文案, 存储值), ...]
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

ROW_LABELS = {
    "output_mode": "输出方式",
    "language": "识别语言",
    "history_limit": "历史上限",
    "auto_stop_silence_s": "静音自停",
    "max_record_s": "单次上限",
    "model_idle_unload_min": "闲置卸载",
    "__mic__": "麦克风设备",
}


# ── 模块层构建助手（不进入 ObjC 类字典）─────────────────────────


def _label(text):
    tf = NSTextField.labelWithString_(text)
    f = tf.frame()
    tf.setFrame_(((24, 0), (112, f.size.height)))
    return tf


def _new_button(title, x, y, w=104, h=26):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setTitle_(title)
    b.setBezelStyle_(1)  # rounded
    return b


def _new_radio(title, x, y, w):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 24))
    b.setButtonType_(NSRadioButton)
    b.setTitle_(title)
    return b


def _new_popup(panel, key, x, y, w=310):
    p = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(x, y, w, 26), False
    )

    if key == "__mic__":
        p.addItemWithTitle_("系统默认")
        devices = recorder.Recorder.enumerate_inputs()[:12]
        names = []
        for dev in devices:
            name = dev["name"] or f"device #{dev['index']}"
            if len(name) > 34:
                name = name[:32] + "…"
            p.addItemWithTitle_(name)
            names.append(dev["name"])
        panel.mic_device_names = names
        panel.popup_values[key] = [""] + names

        current = str(panel.app.config_get("input_device_name", "")).strip().lower()
        lowered = [n.lower()[:32] for n in names]
        idx = next(
            (i for i, n in enumerate(lowered) if n == current[: len(n)]), -1
        )
        if idx >= 0:
            p.selectItemAtIndex_(idx + 1)  # 第 0 项是系统默认
    else:
        defs = POPUP_DEFS[key]
        for text, _v in defs:
            p.addItemWithTitle_(text)
        current = str(panel.app.config_get(key, ""))
        for i, (_t, v) in enumerate(defs):
            if str(v) == current:
                p.selectItemAtIndex_(i)
                break

    p.setTarget_(panel)
    p.setAction_("popupChanged:")
    return p


def _add_popup_row(panel, content, state, key):
    lb = _label(ROW_LABELS.get(key, key))
    lb.setFrameOrigin_(NSMakePoint(24, state["y"] + 7))
    content.addSubview_(lb)
    p = _new_popup(panel, key, 140, state["y"])
    content.addSubview_(p)
    state["y"] -= 36


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
        self.popups = {}          # config_key -> NSPopUpButton
        self.popupValues = {}     # config_key -> [存储值]
        self.mic_device_names = []

        self.modeBaseBtn = None
        self.modeMaxBtn = None
        self.variantFp16Btn = None
        self.variantQ4Btn = None
        self.keyToggleBtn = None
        self.keyPttBtn = None

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
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
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

        state = {"y": h - 56}

        def add_label_row(text):
            lb = _label(text)
            lb.setFrameOrigin_(NSMakePoint(24, state["y"] + 7))
            content.addSubview_(lb)

        def advance(step=36):
            state["y"] -= step

        def gap(step=14):
            state["y"] -= step

        # ── 录音快捷键 ──
        add_label_row("录音快捷键")
        self.hotkeyField = NSTextField.textFieldWithString_(
            symbol_for(str(self.app.config_get("hotkey", "")))
        )
        self.hotkeyField.setFrame_(NSMakeRect(140, state["y"], 168, 26))
        self.hotkeyField.setEditable_(False)
        self.hotkeyField.setBordered_(True)
        self.hotkeyField.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0.5)
        )
        content.addSubview_(self.hotkeyField)

        self.rerecordBtn = _new_button("重新录制", 320, state["y"], 96, 26)
        self.rerecordBtn.setTarget_(self)
        self.rerecordBtn.setAction_("startCapture:")
        content.addSubview_(self.rerecordBtn)
        advance()

        # ── 输出与语言 ──
        _add_popup_row(self, content, state, "output_mode")
        _add_popup_row(self, content, state, "language")
        gap()

        # ── 精度模式（radio pair）──
        add_label_row("精度模式")
        cur = str(self.app.config_get("mode", "base"))
        self.modeBaseBtn = _new_radio("标准 base", 140, state["y"], 130)
        self.modeBaseBtn.setTarget_(self)
        self.modeBaseBtn.setAction_("precisionChanged:")
        content.addSubview_(self.modeBaseBtn)
        self.modeMaxBtn = _new_radio("高精度 turbo", 282, state["y"], 150)
        self.modeMaxBtn.setTarget_(self)
        self.modeMaxBtn.setAction_("precisionChanged:")
        content.addSubview_(self.modeMaxBtn)
        if cur == "max":
            self.modeMaxBtn.setState_(1)
        else:
            self.modeBaseBtn.setState_(1)
        advance()

        # ── 模型量化（radio pair）──
        add_label_row("模型量化")
        cur_v = str(self.app.config_get("model_variant", "fp16"))
        self.variantFp16Btn = _new_radio("fp16", 140, state["y"], 130)
        self.variantFp16Btn.setTarget_(self)
        self.variantFp16Btn.setAction_("variantChanged:")
        content.addSubview_(self.variantFp16Btn)
        self.variantQ4Btn = _new_radio("q4 省内存", 282, state["y"], 150)
        self.variantQ4Btn.setTarget_(self)
        self.variantQ4Btn.setAction_("variantChanged:")
        content.addSubview_(self.variantQ4Btn)
        if cur_v == "q4":
            self.variantQ4Btn.setState_(1)
        else:
            self.variantFp16Btn.setState_(1)
        advance()

        _add_popup_row(self, content, state, "model_idle_unload_min")
        gap()

        # ── 按键模式（radio pair）──
        add_label_row("按键模式")
        cur_hm = str(self.app.config_get("hotkey_mode", "toggle"))
        self.keyToggleBtn = _new_radio("点击切换", 140, state["y"], 130)
        self.keyToggleBtn.setTarget_(self)
        self.keyToggleBtn.setAction_("keyModeChanged:")
        content.addSubview_(self.keyToggleBtn)
        self.keyPttBtn = _new_radio("按住说话", 282, state["y"], 150)
        self.keyPttBtn.setTarget_(self)
        self.keyPttBtn.setAction_("keyModeChanged:")
        content.addSubview_(self.keyPttBtn)
        if cur_hm == "ptt":
            self.keyPttBtn.setState_(1)
        else:
            self.keyToggleBtn.setState_(1)
        advance()

        # ── 麦克风 / 静音自停 / 单次上限 ──
        _add_popup_row(self, content, state, "__mic__")
        _add_popup_row(self, content, state, "auto_stop_silence_s")
        _add_popup_row(self, content, state, "max_record_s")
        gap()

        # ── 历史 ──
        _add_popup_row(self, content, state, "history_limit")
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
            b = _new_button(title, bx, link_y)
            b.setTarget_(self)
            b.setAction_(sel)
            content.addSubview_(b)
            bx += 112

        ver = NSTextField.labelWithString_(f"v{self.app.version_string()}")
        vf = ver.frame()
        ver.setFrameOrigin_(NSMakePoint(w - vf.size.width - 16, link_y + 6))
        ver.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(ver)

        return win

    # ── 事件路由 ─────────────────────────────────────────────────

    def popupChanged_(self, sender):
        for key, btn in self.popups.items():
            if btn == sender:
                idx = int(sender.indexOfSelectedItem())
                values = self.popupValues.get(key, [])
                if 0 <= idx < len(values):
                    self.app.apply_config(key, values[idx])
                return

    def precisionChanged_(self, sender):
        value = "max" if sender == self.modeMaxBtn else "base"
        self.app.apply_config("mode", value)

    def variantChanged_(self, sender):
        value = "q4" if sender == self.variantQ4Btn else "fp16"
        self.app.apply_config("model_variant", value)

    def keyModeChanged_(self, sender):
        value = "ptt" if sender == self.keyPttBtn else "toggle"
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

        if is_cancel_keycode(int(event.keyCode())):
            self._end_capture(cancel=True)
            return None  # 吞掉 Esc，避免关闭窗口

        mods = modifiers_from_flags(int(event.modifierFlags()))
        ch = base_character(event)
        if not mods or not ch:
            return None  # 必须携带至少一个修饰键；吞掉无效按键

        hk = canonical_hotkey(mods, ch)
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


def show_settings(app) -> SettingsPanel:
    """对外入口：创建或聚焦设置窗口。"""
    panel = getattr(app, "_settings_panel", None)
    if panel is None:
        panel = SettingsPanel.alloc().initWithApp_(app)
        app._settings_panel = panel
    panel.show()
    return panel
