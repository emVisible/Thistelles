import unittest

from thistelles import keymap as km


class ModifiersTest(unittest.TestCase):
    def test_all_mods(self):
        flags = km.FLAG_SHIFT | km.FLAG_CTRL | km.FLAG_ALT | km.FLAG_CMD
        self.assertEqual(km.modifiers_from_flags(flags), ["shift", "ctrl", "alt", "cmd"])

    def test_single_cmd(self):
        self.assertEqual(km.modifiers_from_flags(km.FLAG_CMD), ["cmd"])

    def test_none(self):
        self.assertEqual(km.modifiers_from_flags(0), [])


class CancelKeyTest(unittest.TestCase):
    def test_esc_is_cancel(self):
        self.assertTrue(km.is_cancel_keycode(53))

    def test_other_not_cancel(self):
        self.assertFalse(km.is_cancel_keycode(0))


class CanonicalTest(unittest.TestCase):
    def test_orders_modifiers(self):
        # 输入乱序修饰键 → 按 cmd/ctrl/alt/shift 规范排序
        hk = km.canonical_hotkey(["shift", "cmd", "alt"], "'")
        self.assertEqual(hk, "cmd+alt+shift+'")

    def test_dedupes_mods(self):
        hk = km.canonical_hotkey(["cmd", "cmd"], "a")
        self.assertEqual(hk, "cmd+a")

    def test_multi_char_key_untouched(self):
        hk = km.canonical_hotkey(["cmd"], "f5")
        self.assertEqual(hk, "cmd+f5")


class SymbolTest(unittest.TestCase):
    def test_symbols_in_menu_order(self):
        self.assertEqual(km.symbol_for("cmd+shift+'"), "⇧⌘'")

    def test_plain_key_passthrough(self):
        self.assertEqual(km.symbol_for("a"), "A")

    def test_named_key_passthrough(self):
        self.assertEqual(km.symbol_for("ctrl+up"), "⌃up")


class BaseCharFromVkTest(unittest.TestCase):
    def test_letters(self):
        self.assertEqual(km.base_char_from_vk(0), "a")
        self.assertEqual(km.base_char_from_vk(40), "k")

    def test_digits_and_punct(self):
        self.assertEqual(km.base_char_from_vk(18), "1")
        self.assertEqual(km.base_char_from_vk(39), "'")
        self.assertEqual(km.base_char_from_vk(49), " ")

    def test_non_printable_none(self):
        # Esc=53 / F5=96 / 方向键=123 等无基础字符
        self.assertIsNone(km.base_char_from_vk(53))
        self.assertIsNone(km.base_char_from_vk(96))
        self.assertIsNone(km.base_char_from_vk(None))

    def test_covers_printable_fallback(self):
        for ch in km._PRINTABLE_FALLBACK:
            self.assertIn(ch, set(km.VK_TO_CHAR.values()), ch)


if __name__ == "__main__":
    unittest.main()
