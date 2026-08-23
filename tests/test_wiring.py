"""结构化接线测试：防止「配置 ↔ 行为」断链类问题复发。

全部基于 AST 静态分析，不导入任何 GUI/rumps 模块——
在任意平台（含 CI）给出一致的红绿信号（axiom 第三部 §11.2）。

覆盖本仓库实际发生过的事故类别：
1. UI_STRINGS 双语键位不齐 / _tr 引用不存在的键
2. POPUP_DEFS 缺少 ROW_LABELS、_new_popup 忘记写入 popupValues
3. apply_config 分支调用不存在的方法（_set_output 事故）
4. setAction_ 选择器指向 SettingsPanel 上不存在的方法
"""

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = ROOT / "thistelles" / "main.py"
SETTINGS = ROOT / "thistelles" / "settings_window.py"


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _module_dicts(tree):
    """提取模块级字面量字典：{目标名: dict}。"""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    try:
                        out[t.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
    return out


def _class_methods(tree, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


class I18nParityTest(unittest.TestCase):
    """事故：菜单子项移除后遗留死键；双语表手工维护易漂移。"""

    def setUp(self):
        self.strings = _module_dicts(_tree(MAIN))["UI_STRINGS"]

    def test_locales_parity(self):
        zh = set(self.strings["zh-CN"])
        en = set(self.strings["en-US"])
        self.assertEqual(zh, en, f"zh-en 键位不齐: {zh ^ en}")

    def test_tr_literals_exist_in_both_locales(self):
        used = set()
        for node in ast.walk(_tree(MAIN)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                used.add(node.args[0].value)
        zh = set(self.strings["zh-CN"])
        missing = used - zh
        self.assertEqual(missing, set(), f"_tr 引用了不存在的文案键: {missing}")


class PopupWiringTest(unittest.TestCase):
    """事故：弹窗值表漏写导致选择永远无法路由到配置。"""

    def setUp(self):
        self.tree = _tree(SETTINGS)
        self.dicts = _module_dicts(self.tree)

    def test_popup_defs_have_labels(self):
        labels = self.dicts["ROW_LABELS"]
        for key in self.dicts["POPUP_DEFS"]:
            self.assertIn(key, labels, f"POPUP_DEFS[{key}] 缺少 ROW_LABELS 条目")

    def test_new_popup_registers_values_for_both_branches(self):
        src = SETTINGS.read_text(encoding="utf-8")
        # __mic__ 分支与非 mic 分支都必须写入 popupValues
        self.assertIn("panel.popupValues[key] = [\"\"] + names", src)
        self.assertIn("panel.popupValues[key] = [v for _t, v in defs]", src)


class ApplyConfigWiringTest(unittest.TestCase):
    """事故：分支调用不存在的 _set_* 方法，所有设置静默失效。"""

    def test_branch_calls_resolve_to_real_methods(self):
        tree = _tree(MAIN)
        methods = _class_methods(tree, "VoiceInputApp")
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "apply_config"
        )
        called = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        }
        # apply_config 内部允许调用的私有助手白名单之外，必须真实存在
        unknown = {c for c in called if c not in methods}
        self.assertEqual(unknown, set(), f"apply_config 调用了不存在的方法: {unknown}")

    def test_every_defaults_key_is_handled_or_generic(self):
        """每个 DEFAULTS 键要么有显式副作用分支，要么属于「通用保存」白名单。"""
        tree = _tree(MAIN)
        defaults = _module_dicts(_tree(ROOT / "thistelles" / "config.py"))["DEFAULTS"]
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "apply_config"
        )
        handled = set()
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == "key"
            ):
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant):
                        handled.add(comp.value)
        # 「通用保存」白名单：这些键无注册期副作用，各消费点在使用时直读配置。
        # 新增纯存储键时加入此处并注明消费点；需要副作用的必须写显式分支。
        generic_ok = {
            "context_prompt",     # 消费点: main._build_prompt
            "paste_delay_ms",     # 消费点: main._transcribe_async -> ins.deliver
            "waveform_width",     # 消费点: waveform.show
            "waveform_height",    # 消费点: waveform.show
            "waveform_y",         # 消费点: waveform.show
            "output_mode",        # 消费点: main._transcribe_async
            "history_limit",      # 消费点: main._transcribe_async -> hist.add
            "auto_stop_silence_s",  # 消费点: main._poll_amplitude
            "max_record_s",       # 消费点: main._poll_amplitude
        }
        unhandled = set(defaults) - handled - generic_ok
        self.assertEqual(unhandled, set(), f"DEFAULTS 键缺少 apply_config 处理: {unhandled}")


class SelectorWiringTest(unittest.TestCase):
    """事故：按钮 action 选择器指向面板上不存在的方法。"""

    def test_actions_have_methods(self):
        tree = _tree(SETTINGS)
        methods = _class_methods(tree, "SettingsPanel")
        used = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setAction_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                sel = node.args[0].value
                used.add(sel[:-1] + "_" if sel.endswith(":") else sel)
        missing = used - methods
        self.assertEqual(missing, set(), f"选择器缺少对应方法: {missing}")


if __name__ == "__main__":
    unittest.main()
