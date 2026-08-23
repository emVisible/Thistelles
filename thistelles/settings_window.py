"""原生设置窗口：AppKit 程序化布局，所有改动即时生效。

架构约束：

- 本模块只做「控件 ↔ 配置读写 + 应用层副作用」的桥接；
  业务规则仍归属各自模块（层间职责分离）
- 所有配置变更统一经 app.apply_config(key, value) 路由——
  该方法是应用侧副作用与持久化的单一真相源
- 快捷键捕获使用 Quartz CGEventTap 全局吞键（hotkeys.CaptureTap），
  不依赖窗口焦点，捕获期间其它应用不会收到按键；切换

PyObjC 注意事项：NSObject 子类上「必需位置参数 > 0 且不以 _ 结尾」的方法
会被当作 ObjC 选择器做原型校验——带参数的纯辅助函数必须放在模块层。
"""

import logging
import objc
import os
import subprocess
import webbrowser
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSImage,
    NSMakeRect,
    NSPopUpButton,
    NSRadioButton,
    NSRunningApplication,
    NSSwitchButton,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSMakePoint

from . import config as cfg
from . import hotkeys
from . import inserter as ins
from . import recorder
from . import vocab
from .keymap import (
    base_char_from_vk,
    canonical_hotkey,
    flags_to_mods,
    is_cancel_keycode,
    symbol_for,
)

try:
    from AppKit import NSApplicationActivateIgnoringOtherApps
except ImportError:  # 旧系统兜底
    NSApplicationActivateIgnoringOtherApps = 1 << 1

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
    "ui_language": [
        ("中文", "zh-CN"),
        ("English", "en-US"),
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
    "ui_language": "显示语言",
    "history_limit": "历史上限",
    "auto_stop_silence_s": "静音自停",
    "max_record_s": "单次上限",
    "model_idle_unload_min": "闲置卸载",
    "__mic__": "麦克风设备",
}

APP_NAME = "Thistelles"
APP_BUNDLE = "/Applications/Thistelles.app"


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


def _new_checkbox(title, x, y, w):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 24))
    b.setButtonType_(NSSwitchButton)
    b.setTitle_(title)
    return b


def _login_item_enabled() -> bool:
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get the name of every login item'],
            capture_output=True, text=True, timeout=3,
        )
        return APP_NAME in (out.stdout or "").split()
    except Exception:
        logger.debug("settings: login item query failed", exc_info=True)
        return False


def _login_set_enabled(enabled: bool) -> bool:
    if enabled:
        script = (
            'tell application "System Events" to make login item at end '
            f'with properties {{path:"{APP_BUNDLE}", hidden:true}}'
        )
    else:
        script = f'tell application "System Events" to delete login item "{APP_NAME}"'
    try:
        r = subprocess.run(
            ["osascript", "-e", script], capture_output=True, timeout=3
        )
        return r.returncode == 0
    except Exception:
        logger.debug("settings: login item toggle failed", exc_info=True)
        return False


def _new_popup(panel, key, x, y, w=310):
    p = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(x, y, w, 26), False
    )
    panel.popups[key] = p

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
        panel.popupValues[key] = [""] + names

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
        panel.popupValues[key] = [v for _t, v in defs]
        current = panel.app.config_get(key, "")
        for i, (_t, v) in enumerate(defs):
            if cfg.values_match(v, current):  # 数值跨类型容差，回显与行为一致
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
        self.resetHotkeyBtn = None
        self.popups = {}          # config_key -> NSPopUpButton
        self.popupValues = {}     # config_key -> [存储值]
        self.mic_device_names = []

        self.modeBaseBtn = None
        self.modeMaxBtn = None
        self.variantFp16Btn = None
        self.variantQ4Btn = None
        self.keyToggleBtn = None
        self.keyPttBtn = None
        self.loginToggleBtn = None
        self.axStatus = None
        self.axBtn = None

        self.capturing = False
        self.captureListener = None
        self._policy_promoted = False
        return self

    # ── 对外入口 ─────────────────────────────────────────────────

    def show(self):
        # 菜单栏应用是 accessory 政策，macOS 会静默拒绝其激活请求；
        # 临时提升为 regular 再激活（窗口级浮层 + 焦点双保险），关窗时还原
        self._promote_policy()
        self._activate_app()
        if self.window is not None:
            self.window.makeKeyAndOrderFront_(None)
            return
        win = self._build_window()
        win.setReleasedWhenClosed_(False)  # 面板持有引用，防止重复开窗 use-after-free
        win.setLevel_(NSFloatingWindowLevel)  # 打开期间置顶，不被其它应用遮挡
        win.setDelegate_(self)
        win.center()
        self.window = win
        win.orderFrontRegardless()
        win.makeKeyAndOrderFront_(None)

    def windowWillClose_(self, notification):
        self.window = None  # 下次打开重建，控件状态与配置重新同步
        self._demote_policy()

    def _promote_policy(self):
        try:
            app = NSApplication.sharedApplication()
            if int(app.activationPolicy()) != NSApplicationActivationPolicyRegular:
                app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
                self._policy_promoted = True
            # accessory 进程没有 Dock 图标缓存；提升为 regular 后程序化注入，
            # 避免 Dock/任务切换显示空白图标
            if app.applicationIconImage() is None:
                icon_path = os.path.join(
                    os.path.dirname(__file__), "assets", "mic_idle.png"
                )
                img = NSImage.alloc().initWithContentsOfFile_(icon_path)
                if img is not None:
                    app.setApplicationIconImage_(img)
        except Exception:
            logger.debug("settings: policy promote failed", exc_info=True)

    def _demote_policy(self):
        if not self._policy_promoted:
            return
        self._policy_promoted = False
        try:
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception:
            logger.debug("settings: policy demote failed", exc_info=True)

    def _activate_app(self):
        try:  # macOS 14+ 推荐；必须带 IgnoringOtherApps
            ok = NSRunningApplication.currentApplication().activateWithOptions_(
                NSApplicationActivateIgnoringOtherApps
            )
            if ok:
                return
        except Exception:
            pass
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
        self.hotkeyField.setFrame_(NSMakeRect(140, state["y"], 128, 26))
        self.hotkeyField.setEditable_(False)
        self.hotkeyField.setBordered_(True)
        self.hotkeyField.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(13, 0.5)
        )
        content.addSubview_(self.hotkeyField)

        self.rerecordBtn = _new_button("重新录制", 276, state["y"], 84, 26)
        self.rerecordBtn.setTarget_(self)
        self.rerecordBtn.setAction_("startCapture:")
        content.addSubview_(self.rerecordBtn)

        self.resetHotkeyBtn = _new_button("恢复默认", 368, state["y"], 92, 26)
        self.resetHotkeyBtn.setTarget_(self)
        self.resetHotkeyBtn.setAction_("resetHotkey:")
        content.addSubview_(self.resetHotkeyBtn)
        advance()

        # ── 输出与语言 ──
        _add_popup_row(self, content, state, "output_mode")
        _add_popup_row(self, content, state, "language")
        _add_popup_row(self, content, state, "ui_language")
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

        # ── 开机自启 ──
        add_label_row("开机自启")
        self.loginToggleBtn = _new_checkbox("", 140, state["y"], 200)
        self.loginToggleBtn.setTarget_(self)
        self.loginToggleBtn.setAction_("loginChanged:")
        self.loginToggleBtn.setState_(1 if _login_item_enabled() else 0)
        content.addSubview_(self.loginToggleBtn)
        advance()

        # ── 辅助功能权限提示（全局快捷键依赖）──
        ax_ok = ins.accessibility_trusted(prompt=False)
        ax_label = "辅助功能：已授权" if ax_ok else \
            "辅助功能未授权——请在列表中勾选 Thistelles"
        self.axStatus = NSTextField.labelWithString_(ax_label)
        self.axStatus.setFrame_(NSMakeRect(24, 52, 320, 16))
        self.axStatus.setFont_(NSFont.systemFontOfSize_(12))
        self.axStatus.setTextColor_(
            NSColor.secondaryLabelColor() if ax_ok else NSColor.systemRedColor()
        )
        content.addSubview_(self.axStatus)
        if not ax_ok:
            self.axBtn = _new_button("前往授权", 368, 48, 92, 22)
            self.axBtn.setTarget_(self)
            self.axBtn.setAction_("openAccessibility:")
            content.addSubview_(self.axBtn)

        # ── 底部链接行 ──
        link_y = 22
        bx = 20
        for title, sel in (
            ("自定义词典", "openCorrections:"),
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

    def loginChanged_(self, sender):
        enabled = int(sender.state()) == 1
        if not _login_set_enabled(enabled):
            sender.setState_(0 if enabled else 1)  # 失败回滚勾选态
            logger.warning("settings: login item toggle failed")

    # ── 快捷键捕获 ───────────────────────────────────────────────
    # 成熟做法（Raycast/Superwhisper 同类）：捕获期全局吞键——
    # 1) 不依赖本窗口是否聚焦（accessory 应用激活常被拒，本地监听收不到）
    # 2) 按键不会泄漏给其它应用，避免误触系统/其它 app 快捷键

    def startCapture_(self, sender):
        if self.capturing:
            self._finish_capture(cancel=True)
            return
        self.capturing = True
        self.rerecordBtn.setTitle_("按下组合键… Esc 取消")
        self.hotkeyField.setStringValue_("…")
        self.app.suspend_global_hotkeys()
        self.captureListener = hotkeys.CaptureTap(self._capture_key)
        if not self.captureListener.start():
            self._finish_capture(cancel=True)
            self.hotkeyField.setStringValue_("捕获失败（辅助功能权限？）")
            return

    def _capture_key(self, vk: int, flags: int):
        """tap 线程回调：只做纯计算，UI 更新经主线程选择器落地。"""
        if is_cancel_keycode(vk):
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "cancelCapture:", None, False
            )
            return
        mods = flags_to_mods(flags)
        ch = base_char_from_vk(vk)
        if not mods or not ch:
            return  # 必须携带至少一个修饰键；事件已被 tap 吞掉
        hk = canonical_hotkey(mods, ch)
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "applyCapture:", hk, False
        )

    def applyCapture_(self, hk):
        """主线程落地：回显 + 持久化 + 重挂全局热键。"""
        if not self.capturing:
            return
        self.hotkeyField.setStringValue_(symbol_for(hk))
        self.app.apply_config("hotkey", hk)
        self._finish_capture(cancel=False)

    def resetHotkey_(self, sender):
        """恢复出厂默认快捷键；捕获进行中则先取消捕获。"""
        if self.capturing:
            self._finish_capture(cancel=True)
        default = cfg.DEFAULTS["hotkey"]
        self.hotkeyField.setStringValue_(symbol_for(default))
        self.app.apply_config("hotkey", default)

    def cancelCapture_(self, _):
        if not self.capturing:
            return
        self.hotkeyField.setStringValue_(
            symbol_for(str(self.app.config_get("hotkey", "")))
        )
        self._finish_capture(cancel=True)

    def _finish_capture(self, cancel=False):
        if self.captureListener is not None:
            try:
                self.captureListener.stop()
            except Exception:
                pass
            self.captureListener = None
        self.capturing = False
        self.rerecordBtn.setTitle_("重新录制")
        if cancel:
            self.app.resume_global_hotkeys()

    # ── 底部链接 ─────────────────────────────────────────────────

    def openCorrections_(self, sender):
        vocab.reveal_corrections()

    def openDataDir_(self, sender):
        import subprocess

        subprocess.Popen(["open", "-R", vocab.DATA_DIR])

    def openGitHub_(self, sender):
        webbrowser.open(GITHUB_URL)

    def openAccessibility_(self, sender):
        # 先以弹窗方式正式请求一次：让本应用注册进系统「辅助功能」列表，
        # 否则用户在设置面板里找不到可勾选的条目
        try:
            ins.accessibility_trusted(prompt=True)
        except Exception:
            logger.debug("settings: ax prompt failed", exc_info=True)
        try:
            subprocess.Popen(
                ["open",
                 "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"]
            )
        except Exception:
            logger.debug("settings: open AX pane failed", exc_info=True)


def show_settings(app) -> SettingsPanel:
    """对外入口：创建或聚焦设置窗口。"""
    panel = getattr(app, "_settings_panel", None)
    if panel is None:
        panel = SettingsPanel.alloc().initWithApp_(app)
        app._settings_panel = panel
    panel.show()
    return panel
