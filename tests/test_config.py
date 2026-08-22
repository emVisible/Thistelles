import os
import tempfile
import unittest

from thistelles import config as cfg


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = cfg.DATA_DIR
        self._orig_file = cfg.CONFIG_FILE
        cfg.DATA_DIR = self._tmp
        cfg.CONFIG_FILE = os.path.join(self._tmp, "config.json")

    def tearDown(self):
        cfg.DATA_DIR = self._orig_dir
        cfg.CONFIG_FILE = self._orig_file

    def test_defaults_when_missing(self):
        c = cfg.load()
        for key, expected in cfg.DEFAULTS.items():
            self.assertEqual(c[key], expected)

    def test_roundtrip_preserves_values(self):
        cfg.save({"hotkey": "cmd+shift+k", "mode": "max", "custom": 123})
        c = cfg.load()
        self.assertEqual(c["hotkey"], "cmd+shift+k")
        self.assertEqual(c["mode"], "max")
        self.assertEqual(c["custom"], 123)

    def test_invalid_mode_falls_back(self):
        cfg.save({"mode": "bogus"})
        self.assertEqual(cfg.load()["mode"], cfg.DEFAULTS["mode"])

    def test_invalid_output_mode_falls_back(self):
        cfg.save({"output_mode": "telepathy"})
        self.assertEqual(cfg.load()["output_mode"], "paste")

    def test_invalid_hotkey_mode_falls_back(self):
        cfg.save({"hotkey_mode": "yell"})
        self.assertEqual(cfg.load()["hotkey_mode"], "toggle")

    def test_numeric_sanitization(self):
        cfg.save({"auto_stop_silence_s": "abc", "max_record_s": -5})
        c = cfg.load()
        self.assertEqual(c["auto_stop_silence_s"], 0)
        self.assertEqual(c["max_record_s"], 600)

    def test_corrupt_file_returns_defaults(self):
        with open(cfg.CONFIG_FILE, "w") as f:
            f.write("{not json")
        self.assertEqual(cfg.load(), dict(cfg.DEFAULTS))

    def test_non_dict_json_returns_defaults(self):
        cfg.save({})
        with open(cfg.CONFIG_FILE, "w") as f:
            f.write("[1, 2, 3]")
        self.assertEqual(cfg.load(), dict(cfg.DEFAULTS))


if __name__ == "__main__":
    unittest.main()
