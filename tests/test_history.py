import os
import tempfile
import unittest

from thistelles import history as hist


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_file = hist.HISTORY_FILE
        self._orig_dir = hist.DATA_DIR
        hist.DATA_DIR = self._tmp
        hist.HISTORY_FILE = os.path.join(self._tmp, "history.json")

    def tearDown(self):
        hist.DATA_DIR = self._orig_dir
        hist.HISTORY_FILE = self._orig_file

    def test_add_orders_newest_first(self):
        hist.add("first", 10)
        hist.add("second", 10)
        texts = [e["text"] for e in hist.load()]
        self.assertEqual(texts, ["second", "first"])

    def test_limit_trims_oldest(self):
        for i in range(5):
            hist.add(f"m{i}", 3)
        self.assertEqual(len(hist.load()), 3)

    def test_toggle_pin_roundtrip(self):
        hist.add("target", 10)
        state = hist.toggle_pin("target")
        self.assertTrue(state)
        entries = hist.load()
        self.assertTrue(entries[0]["pinned"])
        state = hist.toggle_pin("target")
        self.assertFalse(state)
        self.assertNotIn("pinned", hist.load()[0])

    def test_toggle_pin_unknown_text(self):
        self.assertIsNone(hist.toggle_pin("ghost"))

    def test_pinned_survive_limit_trim(self):
        hist.add("keep-me", 2)
        hist.toggle_pin("keep-me")
        for i in range(5):
            hist.add(f"filler-{i}", 2)
        texts = [e["text"] for e in hist.load()]
        self.assertIn("keep-me", texts)
        self.assertEqual(len(texts), 2)

    def test_ordered_puts_pinned_first(self):
        hist.add("a", 10)
        hist.add("b", 10)
        hist.toggle_pin("a")
        ordered_texts = [e["text"] for e in hist.ordered()]
        self.assertEqual(ordered_texts, ["a", "b"])

    def test_export_writes_all_entries(self):
        hist.add("one", 10)
        hist.add("two", 10)
        hist.toggle_pin("two")
        path = os.path.join(self._tmp, "export.txt")
        count = hist.export_to(path)
        self.assertEqual(count, 2)
        content = open(path, encoding="utf-8").read()
        # 第一个块是置顶条目（带 📌），且整体顺序置顶优先
        first_block = content.split("\n\n")[0]
        self.assertIn("two", first_block)
        self.assertIn("📌", first_block.splitlines()[0])
        self.assertIn("one", content)
        self.assertLess(content.index("two"), content.index("one"))

    def test_corrupt_file_returns_empty(self):
        with open(hist.HISTORY_FILE, "w") as f:
            f.write("not json")
        self.assertEqual(hist.load(), [])


if __name__ == "__main__":
    unittest.main()
