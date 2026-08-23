import unittest

from thistelles import hotkeys as hk
from thistelles.keymap import FLAG_ALT, FLAG_CMD, FLAG_CTRL, FLAG_SHIFT


class ParseHotkeyTest(unittest.TestCase):
    def test_basic(self):
        mods, vk = hk.parse_hotkey("cmd+shift+'")
        self.assertEqual(mods, {"cmd", "shift"})
        self.assertEqual(vk, 39)

    def test_option_alias(self):
        mods, vk = hk.parse_hotkey("option+a")
        self.assertEqual(mods, {"alt"})
        self.assertEqual(vk, 0)

    def test_dash_separator(self):
        mods, vk = hk.parse_hotkey("ctrl-alt-x")
        self.assertEqual(mods, {"ctrl", "alt"})
        self.assertEqual(vk, 7)

    def test_named_key_unsupported(self):
        self.assertEqual(hk.parse_hotkey("cmd+f5"), (set(), None))

    def test_garbage(self):
        self.assertEqual(hk.parse_hotkey(""), (set(), None))


class ComboMatchTest(unittest.TestCase):
    VK = 39
    MODS = {"cmd", "shift"}

    def test_exact_hit(self):
        flags = FLAG_CMD | FLAG_SHIFT
        self.assertTrue(hk.combo_matches(flags, self.VK, self.MODS, self.VK))

    def test_extra_mod_no_hit(self):
        flags = FLAG_CMD | FLAG_SHIFT | FLAG_ALT
        self.assertFalse(hk.combo_matches(flags, self.VK, self.MODS, self.VK))

    def test_missing_mod_no_hit(self):
        self.assertFalse(hk.combo_matches(FLAG_CMD, self.VK, self.MODS, self.VK))

    def test_other_key_no_hit(self):
        self.assertFalse(hk.combo_matches(FLAG_CMD | FLAG_SHIFT, 0, self.MODS, self.VK))

    def test_capslock_bit_ignored(self):
        # 大写锁定等非四修饰位不参与匹配
        caps = 1 << 16
        self.assertTrue(
            hk.combo_matches(FLAG_CMD | FLAG_SHIFT | caps, self.VK, self.MODS, self.VK)
        )


class FlagsToModsTest(unittest.TestCase):
    def test_order_and_names(self):
        out = hk.flags_to_mods(FLAG_SHIFT | FLAG_CMD | FLAG_CTRL | FLAG_ALT)
        self.assertEqual(out, ["shift", "ctrl", "alt", "cmd"])

    def test_empty(self):
        self.assertEqual(hk.flags_to_mods(0), [])


class HotkeyTapDispatchTest(unittest.TestCase):
    """toggle / ptt 分发语义回归（不经 Quartz）。"""

    CMD_SHIFT = FLAG_CMD | FLAG_SHIFT
    VK = 39  # '

    def _tap(self, mode):
        pressed, released = [], []

        def press():
            pressed.append(1)

        def release():
            released.append(1)

        if mode == "ptt":
            tap = hk.HotkeyTap("cmd+shift+'", press, release)
        else:
            tap = hk.HotkeyTap("cmd+shift+'", press, None)
        return tap, pressed, released

    def down(self, tap, flags=CMD_SHIFT, vk=None):
        # True=吞掉（命中）；False=放行
        return tap._dispatch(hk.EVENT_DOWN, flags, self.VK if vk is None else vk)

    def up(self, tap, flags=CMD_SHIFT, vk=None):
        return tap._dispatch(hk.EVENT_UP, flags, self.VK if vk is None else vk)

    def test_toggle_press_once_no_release(self):
        tap, pressed, released = self._tap("toggle")
        self.down(tap)
        self.up(tap)
        self.down(tap)  # 第二次点击仍需触发
        self.assertEqual(len(pressed), 2)
        self.assertEqual(released, [])

    def test_toggle_auto_repeat_ignored(self):
        tap, pressed, released = self._tap("toggle")
        self.down(tap)
        self.down(tap)
        self.down(tap)  # 物理按住时系统连发
        self.assertEqual(len(pressed), 1)
        self.up(tap)
        self.assertEqual(released, [])

    def test_ptt_down_up(self):
        tap, pressed, released = self._tap("ptt")
        self.down(tap)
        self.up(tap)
        self.assertEqual(len(pressed), 1)
        self.assertEqual(len(released), 1)

    def test_ptt_release_mods_first(self):
        # ptt：先松修饰键也应结束按住
        tap, pressed, released = self._tap("ptt")
        self.down(tap)
        tap._dispatch(hk.EVENT_FLAGS, 0, 63)  # 松开 cmd
        self.assertEqual(len(released), 1)

    def test_hit_swallowed_miss_passthrough(self):
        tap, _, _ = self._tap("toggle")
        self.assertTrue(self.down(tap))  # 命中 → 吞掉
        self.assertFalse(self.down(tap, flags=FLAG_CMD | FLAG_ALT, vk=7))  # 未命中 → 放行

    def test_flags_changed_always_pass_through(self):
        tap, pressed, released = self._tap("ptt")
        self.assertFalse(tap._dispatch(hk.EVENT_FLAGS, self.CMD_SHIFT, 63))

    def test_dispatch_returns_bool_only(self):
        # 回归：回调返回值直达 CoreGraphics，只能是 bool 判定的吞/放，
        # 绝不允许哨兵字符串泄漏导致 tap 失效
        tap, _, _ = self._tap("toggle")
        for etype in (hk.EVENT_DOWN, hk.EVENT_UP, hk.EVENT_FLAGS):
            for flags in (self.CMD_SHIFT, FLAG_CMD | FLAG_ALT, 0):
                out = tap._dispatch(etype, flags, self.VK if etype != hk.EVENT_FLAGS else 63)
                self.assertIsInstance(out, bool)

    def test_toggle_never_calls_release_even_on_up(self):
        # 回归：toggle 模式松键绝不触发 release（曾导致点按变按住说话）
        tap, pressed, released = self._tap("toggle")
        self.down(tap)
        result = self.up(tap)
        self.assertEqual(pressed, [1])
        self.assertEqual(released, [])
        self.assertTrue(result)  # 命中键被吞


if __name__ == "__main__":
    unittest.main()
