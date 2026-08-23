"""用户自定义词典（Markdown）。

设计要点：

- 单一文件 corrections.md 承载两件事：
  1. 「错误 → 正确」确定性替换——转写完成后逐条应用（越用越好用的
     唯一可靠路径；调研结论：Whisper 不存在输入法式的模型内学习，
     prompt 只是每次推理的软偏置）
  2. 「正确写法」侧的词条自动注入识别上下文（initial_prompt），
     提升专有名词命中率——无需单独维护热词表
- 所有读取函数在首次调用时确保模板文件存在
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

DATA_DIR = os.path.expanduser("~/.voice-input")
CORRECTIONS_MD = os.path.join(DATA_DIR, "corrections.md")

_ARROW_RE = re.compile(r"^(?:-\s+|[*+]\s+)?(.+?)\s*(?:→|->)\s*(.+?)\s*$")

CORRECTIONS_TEMPLATE = """# 自定义词典 — 让 Thistelles 越用越准的核心配置。
#
# 支持两种条目：
# 1. 纠正替换：`- 错误写法 → 正确写法`，转写完成后逐条确定性替换
# 2. 名词偏好：`- 专有名词`，注入识别上下文提升命中率
#    （带箭头条目的「正确写法」也会自动作为名词偏好）
#
# 以 # 开头的行是注释。保存后下一段录音立即生效，无需重启。

- 隐形千疑 → 引擎迁移
- Thistelles
"""

def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def parse_pairs(md_text: str) -> list[tuple[str, str]]:
    """从 md 文本提取纠正对：`- 错误 → 正确`（兼容 ASCII ->）。"""
    pairs: list[tuple[str, str]] = []
    for line in md_text.splitlines():
        m = _ARROW_RE.match(line.strip())
        if not m:
            continue
        wrong, right = m.group(1).strip(), m.group(2).strip()
        if wrong and right and not wrong.startswith("#"):
            pairs.append((wrong, right))
    return pairs


def load_correction_pairs() -> list[tuple[str, str]]:
    _ensure_dir()
    if not os.path.exists(CORRECTIONS_MD):
        with open(CORRECTIONS_MD, "w", encoding="utf-8") as f:
            f.write(CORRECTIONS_TEMPLATE)
    try:
        return parse_pairs("".join(_read_lines(CORRECTIONS_MD)))
    except Exception:
        logger.exception("vocab: corrections read failed")
        return []


_BARE_TERM_RE = re.compile(r"^(?:[-*+]|\d+[.])\s+(.+)$")


def extract_terms(md_text: str) -> list[str]:
    """提取名词偏好（去重保序）：裸列表行 + 纠正对的「正确写法」侧。"""
    terms: list[str] = []
    seen: set[str] = set()

    def _push(text: str):
        for term in re.split(r"[/、,;；]+", text):
            term = term.strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)

    for line in md_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _ARROW_RE.match(s)
        if m:
            _push(m.group(2))
            continue
        m = _BARE_TERM_RE.match(s)
        if m:
            term = m.group(1).strip()
            if "→" not in term and "->" not in term:
                _push(term)
    return terms


def load_dictionary_terms() -> str:
    """名词偏好拼接为上下文串（initial_prompt 软偏置）。

    与旧热词表的区别：无需单独维护文件，词典本身就是词表；
    prompt 预算有限，取前若干条即够偏置。
    """
    try:
        text = "".join(_read_lines(CORRECTIONS_MD))
    except Exception:
        logger.exception("vocab: dictionary read failed")
        return ""
    return " ".join(extract_terms(text)[:12])


def apply_corrections(text: str, pairs: list[tuple[str, str]]) -> str:
    for wrong, right in pairs:
        text = text.replace(wrong, right)
    return text


def reveal(path: str):
    import subprocess

    subprocess.Popen(["open", "-t", path])


def reveal_corrections():
    ensure_correction_file()
    reveal(CORRECTIONS_MD)


def ensure_correction_file():
    _ensure_dir()
    if not os.path.exists(CORRECTIONS_MD):
        with open(CORRECTIONS_MD, "w", encoding="utf-8") as f:
            f.write(CORRECTIONS_TEMPLATE)
