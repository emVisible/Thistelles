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

# Apple kVK_ANSI 虚拟键码 → 基础字符（shift 无关形态）。
# Apple 虚拟键码（NSEvent.keyCode 与 Quartz CGEvent 键码共用这套编号）
VK_TO_CHAR = {
    0: "a", 11: "b", 8: "c", 2: "d", 14: "e", 3: "f", 5: "g", 4: "h",
    34: "i", 38: "j", 40: "k", 37: "l", 46: "m", 45: "n", 31: "o",
    35: "p", 12: "q", 15: "r", 1: "s", 17: "t", 32: "u", 9: "v",
    13: "w", 7: "x", 16: "y", 6: "z",
    29: "0", 18: "1", 19: "2", 20: "3", 21: "4", 23: "5", 22: "6",
    26: "7", 28: "8", 25: "9",
    27: "-", 24: "=", 33: "[", 30: "]", 41: ";", 39: "'", 43: ",",
    47: ".", 44: "/", 42: "\\", 50: "`", 49: " ",
}


def base_char_from_vk(keycode) -> str | None:
    """虚拟键码转基础字符；不可打印（F 键/方向键等）返回 None。"""
    try:
        return VK_TO_CHAR.get(int(keycode))
    except (TypeError, ValueError):
        return None


CHAR_TO_VK = {ch: vk for vk, ch in VK_TO_CHAR.items()}


def vk_for_char(ch: str) -> int | None:
    """基础字符转虚拟键码；未收录返回 None。"""
    return CHAR_TO_VK.get(ch)


# 与 Quartz kCGEventFlagMask* 位一致（NSEvent 设备无关修饰位同源）
MOD_FLAGS = {"cmd": FLAG_CMD, "ctrl": FLAG_CTRL, "alt": FLAG_ALT, "shift": FLAG_SHIFT}


def flags_to_mods(flags: int) -> list[str]:
    """修饰位 → 规范命名列表（按 cmd+ctrl+alt+shift 展示惯例排序）。"""
    out = []
    for name in ("shift", "ctrl", "alt", "cmd"):
        if flags & MOD_FLAGS[name]:
            out.append(name)
    return out


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
    """配置串转展示符号；修饰键按 macOS 菜单惯例排序（⇧⌃⌥⌘）。"""
    parts = [p for p in hotkey.lower().split("+") if p]
    mods = "".join(_SYMBOLS[n] for n in ("shift", "ctrl", "alt", "cmd") if n in parts)
    keys = [p for p in parts if p not in ("shift", "ctrl", "alt", "cmd", "option")]
    if not keys:
        return mods
    key = keys[-1].upper() if len(keys[-1]) == 1 else keys[-1]
    return mods + key
