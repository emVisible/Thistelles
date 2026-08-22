"""macOS notification delivery with launch-context guards and fallbacks.

两条实战发现的硬约束：

1. UNUserNotificationCenter 要求真实的应用包上下文——在裸解释器
   （无 Info.plist / bundleIdentifier）里调用会让 ObjC 异常穿透 PyObjC，
   直接终止整个进程，Python 层无法捕获。因此调用前必须守卫。
2. 即使有合法 bundle，投递也需要用户授予通知权限；首次未授权时请求会
   弹系统授权框。

投递决策表：

- 无 bundle 上下文（终端/开发启动）      → osascript 通知（回退通道）
- 有 bundle 且已授权                     → UserNotifications 富通知
- 有 bundle 但被拒绝 / 投递失败           → osascript 兜底，不静默丢失
"""

import logging
import subprocess
import threading

logger = logging.getLogger(__name__)

_auth_requested = threading.Event()
_authorized = False


def _bundle_context_valid() -> bool:
    """仅当进程携带真实应用包标识（bundleIdentifier 非空）时返回 True。"""
    try:
        from Foundation import NSBundle

        return bool(NSBundle.mainBundle().bundleIdentifier())
    except Exception:
        return False


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _osa_notify(title: str, subtitle: str = "", body: str = "") -> bool:
    script = 'display notification "{}" with title "{}" subtitle "{}"'.format(
        _esc(body or ""),
        _esc(title),
        _esc(subtitle),
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", script], capture_output=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        logger.exception("notify: osascript fallback failed")
        return False


def _un_request_authorization() -> bool:
    """请求 alert+sound 授权；阻塞等待系统弹框结果至多 3 秒。"""
    global _authorized
    done = threading.Event()

    def completion(granted: bool, error) -> None:
        global _authorized
        _authorized = bool(granted)
        if granted:
            logger.info("notify: authorization granted")
        else:
            logger.warning(
                "notify: authorization denied — falling back to osascript"
            )
        done.set()

    from UserNotifications import (
        UNAuthorizationOptionAlert,
        UNAuthorizationOptionSound,
        UNUserNotificationCenter,
    )

    options = int(UNAuthorizationOptionAlert | UNAuthorizationOptionSound)
    UNUserNotificationCenter.currentNotificationCenter().requestAuthorizationWithOptions_completionHandler_(
        options, completion
    )
    done.wait(timeout=3)
    return _authorized


def _un_post(title: str, subtitle: str = "", body: str = "") -> bool:
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
        if subtitle:
            content.setSubtitle_(subtitle)
        if body:
            content.setBody_(body)
        trigger = UNTimeIntervalNotificationTrigger.triggerWithTimeInterval_repeats_(
            0.1, False
        )
        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            "thistelles", content, trigger
        )
        center.addNotificationRequest_withCompletionHandler_(
            request, None
        )
        return True
    except Exception:
        # 此处异常可能为 ObjC 级；任何失败都视为通道不可用
        logger.exception("notify: un channel failed")
        return False


def ensure_authorization() -> bool:
    """幂等触发授权请求（仅 bundle 上下文有意义）。"""
    global _authorized
    if not _bundle_context_valid():
        return False
    if _auth_requested.is_set():
        return _authorized
    _auth_requested.set()
    try:
        _authorized = _un_request_authorization()
    except Exception:
        logger.exception("notify: authorization flow failed")
    return _authorized


def post(title: str, subtitle: str = "", body: str = ""):
    """对外唯一投递入口：按启动上下文自动选择通道，永不静默丢失。"""
    if not _bundle_context_valid():
        _osa_notify(title, subtitle, body)
        return

    if not _auth_requested.is_set():
        ensure_authorization()

    if _authorized:
        try:
            if _un_post(title, subtitle, body):
                return
        except Exception:
            logger.exception("notify: un post crashed, falling back")

    _osa_notify(title, subtitle, body)
