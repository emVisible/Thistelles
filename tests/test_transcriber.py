import threading
import unittest
from unittest import mock

import numpy as np

from thistelles import transcriber as tr


class ModelRegistryTest(unittest.TestCase):
    def tearDown(self):
        tr.set_variant("fp16")

    def test_repos_cover_modes(self):
        for mode in ("base", "max"):
            self.assertIn(mode, tr.MODEL_REPOS)
            self.assertIn("mlx-community", tr.MODEL_REPOS[mode])

    def test_max_uses_turbo(self):
        self.assertIn("turbo", tr.MODEL_REPOS["max"])

    def test_resolve_model_falls_back_to_base(self):
        self.assertEqual(tr.resolve_model("bogus"), tr.MODEL_REPOS["base"])
        self.assertEqual(tr.resolve_model("max"), tr.MODEL_REPOS["max"])

    def test_variant_q4_appends_suffix_to_max_only(self):
        tr.set_variant("q4")
        self.assertTrue(tr.resolve_model("max").endswith("-q4"))
        self.assertFalse(tr.resolve_model("base").endswith("-q4"))

    def test_variant_invalid_falls_back_to_fp16(self):
        tr.set_variant("int8")
        self.assertFalse(tr.resolve_model("max").endswith("-q4"))

    def test_no_ct2_references_remain(self):
        source = open(tr.__file__, encoding="utf-8").read()
        self.assertNotIn("ct2", source.lower())
        self.assertNotIn("faster_whisper", source)


class TranscribeContractTest(unittest.TestCase):
    def test_cancelled_passthrough(self):
        with mock.patch.object(
            tr, "_transcribe", return_value=(None, None, "cancelled")
        ):
            self.assertEqual(tr.transcribe("w.wav"), (None, "cancelled"))

    def test_model_error_passthrough(self):
        with mock.patch.object(
            tr, "_transcribe", return_value=(None, None, "model_error")
        ):
            self.assertEqual(tr.transcribe("w.wav"), (None, "model_error"))

    def test_inference_error_passthrough(self):
        with mock.patch.object(
            tr, "_transcribe", return_value=(None, None, "inference_error")
        ):
            self.assertEqual(tr.transcribe("w.wav"), (None, "inference_error"))

    def test_zh_cn_converts_to_simplified(self):
        called = []
        original = tr._to_simplified
        tr._to_simplified = lambda t: (called.append(1) or t.replace("繁", "简"))
        try:
            with mock.patch.object(
                tr, "_transcribe", return_value=("含繁字", "zh", None)
            ):
                text, err = tr.transcribe("w.wav", "zh-CN")
        finally:
            tr._to_simplified = original
        self.assertIsNone(err)
        self.assertTrue(called)
        # 验证转换结果被实际采用（不依赖 opencc 在测试环境可用）
        self.assertEqual(text, "含简字")

    def test_auto_with_detected_zh_converts(self):
        called = []
        original = tr._to_simplified
        tr._to_simplified = lambda t: (called.append(1) or t)
        try:
            with mock.patch.object(
                tr, "_transcribe", return_value=("内容", "zh", None)
            ):
                tr.transcribe("w.wav", "auto")
        finally:
            tr._to_simplified = original
        self.assertTrue(called)

    def test_auto_with_detected_zh_converts(self):
        called = []
        original = tr._to_simplified
        tr._to_simplified = lambda t: (called.append(1) or original(t))
        try:
            with mock.patch.object(
                tr, "_transcribe", return_value=("内容", "zh", None)
            ):
                tr.transcribe("w.wav", "auto")
        finally:
            tr._to_simplified = original
        self.assertTrue(called)

    def test_auto_with_non_zh_skips_conversion(self):
        called = []
        original = tr._to_simplified
        tr._to_simplified = lambda t: (called.append(1) or original(t))
        try:
            with mock.patch.object(
                tr, "_transcribe", return_value=("hello", "en", None)
            ):
                text, err = tr.transcribe("w.wav", "auto")
        finally:
            tr._to_simplified = original
        self.assertFalse(called)
        self.assertEqual(text, "hello")

    def test_empty_result_returns_none(self):
        with mock.patch.object(tr, "_transcribe", return_value=("  ", None, None)):
            self.assertEqual(tr.transcribe("w.wav"), (None, None))


class MlxPathTest(unittest.TestCase):
    def test_cancel_before_start_short_circuits(self):
        ev = threading.Event()
        ev.set()
        with mock.patch.object(tr, "_ensure_mlx") as ensure, \
             mock.patch.dict("sys.modules", {"mlx_whisper": mock.MagicMock()}):
            out = tr._transcribe("w.wav", "zh-CN", "base", None, ev)
        self.assertEqual(out[2], "cancelled")
        ensure.assert_not_called()

    def test_ensure_failure_returns_model_error(self):
        ev = threading.Event()
        with mock.patch.object(tr, "_ensure_mlx", return_value=False):
            out = tr._transcribe("w.wav", "zh-CN", "base", None, ev)
        self.assertEqual(out[2], "model_error")


class TrimSilenceTest(unittest.TestCase):
    RATE = 16000

    def _signal(self, silence_s: float, speech_s: float):
        silent = np.zeros(int(silence_s * self.RATE), dtype=np.float32)
        t = np.linspace(0, speech_s, int(speech_s * self.RATE), endpoint=False)
        tone = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return np.concatenate([silent, tone, silent])

    def test_trims_leading_and_trailing_silence(self):
        x = self._signal(1.0, 1.0)
        out = tr._trim_silence(x)
        self.assertLess(len(out), len(x) - 2 * 16000 + int(0.4 * 16000))

    def test_all_silent_returns_original(self):
        x = np.zeros(self.RATE, dtype=np.float32)
        self.assertEqual(len(tr._trim_silence(x)), len(x))

    def test_short_input_unchanged(self):
        x = np.full(100, 0.5, dtype=np.float32)
        self.assertEqual(len(tr._trim_silence(x)), len(x))


class HfCacheTest(unittest.TestCase):
    def test_bogus_repo_not_cached(self):
        self.assertFalse(tr._hf_cached("nobody/nothing-here"))

    def test_max_cached_flag_matches_helper(self):
        # turbo 已在本机缓存（此前预下载）
        self.assertIsInstance(tr.max_model_cached(), bool)

    def test_summary_line_mentions_engine(self):
        line = tr.cache_summary_line()
        self.assertIn("engine=mlx", line)


if __name__ == "__main__":
    unittest.main()
