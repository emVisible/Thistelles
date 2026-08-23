"""Quartz CGEventTap 全局热键层。

为什么不用 pynput：其 darwin 后端在监听线程内经 ctypes 调用
TSMGetInputSourceProperty 等 HIToolbox API，新版 macOS 对这些调用
强制主线程断言（dispatch_assert_queue_fail → SIGTRAP），按键即闪退
（见 DiagnosticReports python3.12-*.ips 崩溃帧）。

CGEventTap 回调同样发生在 tap 线程，但我们只触碰 CGEvent 数值字段，
不进 HIToolbox/TSM，无主线程约束；辅助功能权限要求与原方案一致。

提供两种 tap：
- HotkeyTap  ：全局录音热键（toggle / ptt），命中组合键时吞掉事件
- CaptureTap ：设置窗口「重新录制」捕获期全局吞键（替代 pynput suppress）
"""

import logging
import threading

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CFRunLoopStop,
        CFMachPortInvalidate,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventTapCreate,
        CGEventTapEnable,
        kCGHeadInsertEventTap,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventFlagsChanged,
        kCGEventTapOptionDefault,
        kCGEventTapOptionListenOnly,
        kCGKeyboardEventKeycode,
        kCGSessionEventTap,
        kCFRunLoopCommonModes,
    )
    _QUARTZ_OK = True
except ImportError:  # 非 macOS 环境：纯函数仍可测试
    _QUARTZ_OK = False

from .keymap import (
    FLAG_ALT,
    FLAG_CMD,
    FLAG_CTRL,
    FLAG_SHIFT,
    MOD_FLAGS,
    flags_to_mods,
    vk_for_char,
)

_ALL_MOD_MASK = FLAG_CMD | FLAG_CTRL | FLAG_ALT | FLAG_SHIFT

logger = logging.getLogger(__name__)

# 事件类型统一别名：无 Quartz 环境（测试/CI）使用数值占位，语义一致
if _QUARTZ_OK:
    EVENT_DOWN = kCGEventKeyDown
    EVENT_UP = kCGEventKeyUp
    EVENT_FLAGS = kCGEventFlagsChanged
    _EVENT_MASK = (1 << EVENT_DOWN) | (1 << EVENT_UP) | (1 << EVENT_FLAGS)
else:
    EVENT_DOWN, EVENT_UP, EVENT_FLAGS = 10, 12, 14
    _EVENT_MASK = 0


def parse_hotkey(config_str: str):
    """`cmd+shift+'` → (mods:set[str], vk:int|None)；无法解析返回 ({}, None)。"""
    mods: set[str] = set()
    base: str | None = None
    for part in config_str.lower().replace("-", "+").split("+"):
        part = part.strip()
        if not part:
            continue
        if part in MOD_FLAGS or part == "option":
            mods.add("alt" if part == "option" else part)
        else:
            base = part
    if base is None or len(base) != 1:
        return set(), None
    vk = vk_for_char(base)
    if vk is None:
        return set(), None
    return mods, vk


def combo_matches(flags: int, keycode: int, mods: set[str], vk: int) -> bool:
    """事件是否精确命中组合键：目标修饰全按住，且无多余修饰。"""
    if keycode != vk:
        return False
    required = 0
    for m in mods:
        required |= MOD_FLAGS[m]
    active = flags & _ALL_MOD_MASK
    return (active & required) == required and (active & ~required) == 0


class _BaseTap:
    """CGEventTap + 独立 CFRunLoop 线程的公共骨架。"""

    def __init__(self, listen_only: bool, callback):
        self._port = None
        self._source = None
        self._rl = None
        self._thread: threading.Thread | None = None
        self._callback = callback  # (proxy, etype, event) -> event|None
        self._listen_only = listen_only

    def start(self):
        if not _QUARTZ_OK:
            logger.error("tap: Quartz unavailable")
            return False
        opts = kCGEventTapOptionListenOnly if self._listen_only else kCGEventTapOptionDefault
        port = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            opts,
            _EVENT_MASK,
            self._on_event,
            None,
        )
        if port is None:
            logger.error("hotkey: CGEventTapCreate failed (accessibility?)")
            return False
        self._port = port
        self._source = CFMachPortCreateRunLoopSource(None, port, 0)
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # 等待 runloop 就绪，避免 stop() 早于 start 的竞态
        self._ready.wait(timeout=2.0)
        logger.debug("tap started (%s)", type(self).__name__)
        return True

    def _run(self):
        CFRunLoopAddSource(CFRunLoopGetCurrent(), self._source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._port, True)
        self._rl = CFRunLoopGetCurrent()
        if getattr(self, "_ready", None):
            self._ready.set()
        CFRunLoopRun()

    def stop(self):
        rl, port = self._rl, self._port
        self._rl = self._port = None
        if rl is not None:
            CFRunLoopStop(rl)
        if port is not None:
            try:
                CGEventTapEnable(port, False)
                CFMachPortInvalidate(port)
            except Exception:
                logger.debug("tap teardown issue", exc_info=True)
        self._thread = None

    def _on_event(self, proxy, etype, event, refcon):
        return self._callback(proxy, etype, event)


class HotkeyTap(_BaseTap):
    """录音热键。toggle / ptt 共用同一常驻 tap：
    - 组合键变更走 update_hotkey() 原地更新，不重建端口
      （频繁销毁重建会让系统逐渐拒绝 CGEventTapCreate）
    - ptt 语义由调用方在回调里按当前模式自行分流
    """

    def __init__(self, hotkey_str: str, on_press, on_release=None):
        super().__init__(listen_only=False, callback=self._handle)
        self._mods, self._vk = parse_hotkey(hotkey_str)
        if not self._mods or self._vk is None:
            raise ValueError(f"unsupported hotkey: {hotkey_str!r}")
        self._press = on_press
        self._release = on_release
        self._armed = False

    def update_hotkey(self, hotkey_str: str):
        """原地换键；解析失败抛 ValueError 且保持原配置不变。"""
        mods, vk = parse_hotkey(hotkey_str)
        if not mods or vk is None:
            raise ValueError(f"unsupported hotkey: {hotkey_str!r}")
        self._mods, self._vk = mods, vk
        self._armed = False

    def _handle(self, proxy, etype, event):
        # 注意：本回调返回值直达 CoreGraphics——必须返回原始 event（放行）
        # 或 None（吞掉）。绝不能让其它类型泄漏出去，否则 tap 失效。
        try:
            swallow = self._dispatch(
                etype,
                int(CGEventGetFlags(event)),
                int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)),
            )
        except Exception:
            logger.exception("hotkey: dispatch error")
            return event
        return None if swallow else event

    def _dispatch(self, etype, flags: int, kc: int) -> bool:
        """纯逻辑判定：True=吞掉（命中组合键），False=放行。可单测。"""
        hit = combo_matches(flags, kc, self._mods, self._vk)
        mods_held = all(flags & MOD_FLAGS[m] for m in self._mods)

        if etype == EVENT_FLAGS:
            # ptt：先松开修饰键也结束按住
            if self._armed and not mods_held and self._release is not None:
                self._armed = False
                self._release()
            return False

        if etype == EVENT_UP:
            if hit:
                had = self._armed
                self._armed = False  # 复位以支持 toggle 再次按下
                if had and self._release is not None:
                    self._release()
            return hit

        # keyDown；_armed 兼防物理按住时的系统 auto-repeat 连发
        if hit and not self._armed:
            self._armed = True
            self._press()
        return hit


class CaptureTap(_BaseTap):
    """捕获期全局吞所有 keyDown/keyUp；回调收到 (vk:int, flags:int)。

    仅吞键盘，不解析字符（字符解析由调用方经 keymap 完成），
    因此本类不触碰任何 TSM/HIToolbox API。
    """

    def __init__(self, on_key):
        super().__init__(listen_only=False, callback=self._handle)
        self._on_key = on_key

    def _handle(self, proxy, etype, event):
        if etype == kCGEventFlagsChanged:
            return event  # 修饰键本身放行，无副作用
        kc = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
        flags = int(CGEventGetFlags(event))
        try:
            self._on_key(kc, flags)
        except Exception:
            logger.exception("capture: callback error")
        return None  # 全部吞掉
