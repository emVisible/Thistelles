import threading
import time
import unittest
from unittest import mock

from thistelles import inserter as ins


class InserterTest(unittest.TestCase):
    def setUp(self):
        self.clipboard = {}
        self.paste_calls = []

        patchers = [
            mock.patch.object(ins, "get_clipboard", side_effect=lambda: self.clipboard.get("v")),
            mock.patch.object(ins, "set_clipboard", side_effect=lambda t: self.clipboard.__setitem__("v", t)),
            mock.patch.object(
                ins, "paste_at_cursor", side_effect=lambda: self.paste_calls.append(1) or True
            ),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def _run(self, mode):
        return ins.deliver("hello", mode, 1)

    def test_clipboard_mode_never_pastes(self):
        pasted, eff = self._run("clipboard")
        self.assertFalse(self.paste_calls)
        self.assertEqual((pasted, eff), (False, "clipboard"))
        self.assertEqual(self.clipboard["v"], "hello")

    def test_paste_mode_pastes_and_restores(self):
        self.clipboard["v"] = "previous"
        ins._RESTORE_DELAY_S = 0.05
        try:
            pasted, eff = self._run("paste")
        finally:
            restore_delay = ins._RESTORE_DELAY_S
        self.assertTrue(pasted)
        self.assertEqual(eff, "paste")
        self.assertEqual(len(self.paste_calls), 1)
        self.assertEqual(self.clipboard["v"], "hello")
        deadline = time.time() + 2
        while time.time() < deadline and self.clipboard["v"] != "previous":
            time.sleep(0.02)
        self.assertEqual(self.clipboard["v"], "previous")

    def test_both_mode_keeps_text_in_clipboard(self):
        pasted, eff = self._run("both")
        self.assertTrue(pasted)
        self.assertEqual(eff, "both")
        self.assertEqual(len(self.paste_calls), 1)
        self.assertEqual(self.clipboard["v"], "hello")

    def test_no_accessibility_falls_back_to_clipboard_only(self):
        with mock.patch.object(ins, "accessibility_trusted", return_value=False):
            pasted, eff = self._run("paste")
        self.assertEqual((pasted, eff), (False, "clipboard"))
        self.assertFalse(self.paste_calls)

    def test_empty_prev_clipboard_restore_is_noop(self):
        ins._RESTORE_DELAY_S = 0.05
        self._run("paste")  # clipboard was empty before; nothing to restore
        time.sleep(0.2)
        self.assertEqual(self.clipboard["v"], "hello")


if __name__ == "__main__":
    unittest.main()
