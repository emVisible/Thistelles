import unittest

from thistelles import vocab


class ParseTermsTest(unittest.TestCase):
    def test_extracts_list_items(self):
        md = "# 注释\n- Thistelles\n- 引擎迁移\n"
        self.assertEqual(vocab.parse_terms(md), ["Thistelles", "引擎迁移"])

    def test_skips_correction_format_lines(self):
        md = "- 错误 → 正确\n- 正常词条\n"
        self.assertEqual(vocab.parse_terms(md), ["正常词条"])

    def test_empty_returns_empty(self):
        self.assertEqual(vocab.parse_terms("# only comment\n"), [])


class ParsePairsTest(unittest.TestCase):
    def test_unicode_arrow(self):
        self.assertEqual(vocab.parse_pairs("- 隐形千疑 → 引擎迁移\n"),
                         [("隐形千疑", "引擎迁移")])

    def test_ascii_arrow_tolerated(self):
        self.assertEqual(vocab.parse_pairs("- wrong -> right\n"),
                         [("wrong", "right")])


class ApplyCorrectionsTest(unittest.TestCase):
    def test_replaces_all_pairs_in_order(self):
        pairs = [("隐形千疑", "引擎迁移"), ("端道端", "端到端")]
        text = "这是隐形千疑的端道端测试"
        out = vocab.apply_corrections(text, pairs)
        # 逐条顺序替换
        self.assertEqual(out, "这是引擎迁移的端到端测试")

    def test_no_pairs_is_identity(self):
        self.assertEqual(vocab.apply_corrections("原文", []), "原文")


if __name__ == "__main__":
    unittest.main()
