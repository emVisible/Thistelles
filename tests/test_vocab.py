import unittest

from thistelles import vocab


class ParsePairsTest(unittest.TestCase):
    def test_unicode_arrow(self):
        self.assertEqual(vocab.parse_pairs("- 隐形千疑 → 引擎迁移\n"),
                         [("隐形千疑", "引擎迁移")])

    def test_ascii_arrow_tolerated(self):
        self.assertEqual(vocab.parse_pairs("- wrong -> right\n"),
                         [("wrong", "right")])

    def test_bare_terms_ignored_by_pair_parser(self):
        self.assertEqual(vocab.parse_pairs("- Thistelles\n"), [])


class ExtractTermsTest(unittest.TestCase):
    def test_extracts_bare_list_items(self):
        md = "# 注释\n- Thistelles\n- 引擎迁移\n"
        self.assertEqual(vocab.extract_terms(md), ["Thistelles", "引擎迁移"])

    def test_pair_right_side_is_term(self):
        md = "- 隐形千疑 → 引擎迁移\n"
        self.assertEqual(vocab.extract_terms(md), ["引擎迁移"])

    def test_mixed_dedup_case_insensitive(self):
        md = "- MLX\n- mlx → MLX\n"
        self.assertEqual(vocab.extract_terms(md), ["MLX"])

    def test_separators_split(self):
        md = "- 端到端/E2E、引擎迁移\n"
        self.assertEqual(vocab.extract_terms(md), ["端到端", "E2E", "引擎迁移"])

    def test_numbered_list_and_comments_skipped(self):
        md = "# only comment\n1. 专有名词\n"
        self.assertEqual(vocab.extract_terms(md), ["专有名词"])

    def test_empty_returns_empty(self):
        self.assertEqual(vocab.extract_terms("# only comment\n"), [])


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
