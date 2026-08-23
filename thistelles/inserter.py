"""Deliver transcribed text: copy to clipboard and/or paste at cursor.

Paste is simulated with a synthetic Cmd+V via the Quartz CGEvent API,
which requires Accessibility permission (already required for global hotkeys).
"""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

_VK_V = 0x09  # kVK_ANSI_V
_PASTE_SETTLE_S = 0.15
_RESTORE_DELAY_S = 0.6

try:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        kCGEventFlagMaskCommand,
        kCGHIDEventTap,
    )
    _QUARTZ_OK = True
except Exception:
    _QUARTZ_OK = False


_AX_PROMPT = None
try:
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        kAXTrustedCheckOptionPrompt,
    )
    _AX_PROMPT = (AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)
except ImportError:
    pass  # 依赖缺失：下方降级为不可用，并以 warning 提示


def accessibility_trusted(prompt: bool = True) -> bool:
    """Check (and optionally prompt for) Accessibility permission.

    prompt=True 会弹出系统授权框并把应用注册进「辅助功能」列表。
    """
    if _AX_PROMPT is None:
        # 依赖缺失时无法检测也无法请求——按未授权处理并大声说出来，
        # 绝不能静默 False 让用户在系统设置里找不到原因
        logger.warning(
            "accessibility: ApplicationServices unavailable "
            "(pyobjc-framework-ApplicationServices missing?) — treat as untrusted"
        )
        return False
    try:
        options = {kAXTrustedCheckOptionPrompt: bool(prompt)}
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        logger.warning("accessibility: check failed", exc_info=True)
        return False


def paste_at_cursor() -> bool:
    """Synthesize Cmd+V. Returns True if events were posted."""
    if not _QUARTZ_OK:
        logger.error("paste: Quartz unavailable")
        return False
    try:
        down_v = CGEventCreateKeyboardEvent(None, _VK_V, True)
        up_v = CGEventCreateKeyboardEvent(None, _VK_V, False)
        CGEventSetFlags(down_v, kCGEventFlagMaskCommand)
        CGEventSetFlags(up_v, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, down_v)
        time.sleep(0.01)
        CGEventPost(kCGHIDEventTap, up_v)
        return True
    except Exception:
        logger.exception("paste: failed to post events")
        return False


def get_clipboard() -> str | None:
    try:
        out = subprocess.run(
            ["pbpaste"], capture_output=True, timeout=2
        ).stdout
        return out.decode("utf-8", errors="replace")
    except Exception:
        return None


def set_clipboard(text: str) -> bool:
    try:
        proc = subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"), timeout=2
        )
        return proc.returncode == 0
    except Exception:
        return False


def deliver(text: str, mode: str, delay_ms: int) -> tuple[bool, str]:
    """Deliver text per output mode.

    Returns (pasted, effective_mode). Clipboard always ends up with a usable
    result: in 'both' it keeps the text; in 'paste' the previous clipboard
    content is restored after the target app consumes it.
    """
    if not accessibility_trusted(prompt=False):
        set_clipboard(text)
        return False, "clipboard"

    prev_clipboard = get_clipboard()
    set_clipboard(text)

    # 粘贴动作必须先经模式门禁——仅复制模式下绝不触发 CGEvent。
    if mode == "clipboard":
        return False, "clipboard"

    time.sleep(delay_ms / 1000.0)
    pasted = paste_at_cursor()

    if mode == "both":
        return pasted, "both"

    if pasted and mode == "paste":
        def restore():
            time.sleep(_RESTORE_DELAY_S)
            if prev_clipboard:
                set_clipboard(prev_clipboard)

        import threading
        threading.Thread(target=restore, daemon=True).start()
        return True, "paste"

    return False, "clipboard"
