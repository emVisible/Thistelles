"""Hotkey capture: NSEvent → canonical config string + display symbols.

纯函数模块（无 GUI 依赖），便于单元测试。
"""

# macOS 菜单惯例的修饰键展示顺序
_MODIFIER_ORDER = ["shift", "ctrl", "alt", "cmd"]
_SYMBOLS = {"cmd": "⌘", "ctrl": "⌃", "alt": "⌥", "shift": "⇧"}

# NSEvent.modifierFlags 的设备无关位
FLAG_SHIFT = 1 << 17
FLAG_CTRL = 1 << 18
FLAG_ALT = 1 << 19
FLAG_CMD = 1 << 20

_ESC_KEYCODE = 53

_PRINTABLE_FALLBACK = set(
    "abcdefghijklmnopqrstuvwxyz0123456789',./;[]\\-=`"
)


def modifiers_from_flags(flags: int) -> list[str]:
    mods = []
    if flags & FLAG_SHIFT:
        mods.append("shift")
    if flags & FLAG_CTRL:
        mods.append("ctrl")
    if flags & FLAG_ALT:
        mods.append("alt")
    if flags & FLAG_CMD:
        mods.append("cmd")
    return mods


def is_cancel_keycode(keycode: int) -> bool:
    return keycode == _ESC_KEYCODE


def base_character(event) -> str | None:
    """提取按键的基础字符（忽略修饰键影响）；不可打印返回 None。

    charactersIgnoringModifiers 给出未加 shift 的基础字符，
    这正是配置串需要的形态（如 ⇧+' 记作 ' 而非 "）。
    """
    chars = event.charactersIgnoringModifiers() or ""
    if len(chars) != 1:
        return None
    ch = chars.lower()
    if ch in _PRINTABLE_FALLBACK or ch == " ":
        return ch
    return None


def canonical_hotkey(mods: list[str], key_char: str) -> str:
    """修饰键规范化排序后拼接配置串，如 cmd+shift+'。"""
    order = {"cmd": 0, "ctrl": 1, "alt": 2, "shift": 3}
    unique = sorted(set(mods), key=lambda m: order.get(m, 99))
    return "+".join(unique + [key_char])


def symbol_for(hotkey: str) -> str:
    """配置串转菜单/窗口展示符号，如 cmd+shift+' → ⌘⇧'。"""
    mods = []
    key = ""
    for part in [p for p in hotkey.lower().split("+") if p]:
        if part in _SYMBOLS:
            mods.append(_SYMBOLS[part])
        else:
            key = part.upper() if len(part) == 1 else part
    return "".join(mods) + key
