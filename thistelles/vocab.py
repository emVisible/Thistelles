"""用户词汇文件管理：热词表与纠正词典（均为 Markdown）。

设计要点：

- 旧版 hotwords.txt 自动迁移为 hotwords.md（幂等：md 存在则跳过）
- 纠正词典 corrections.md 采用 `- 错误 → 正确` 行格式，转写完成后做
  确定性替换——这是「越用越好用」的唯一可靠路径（调研结论：
  Whisper 不存在输入法式的模型内学习，prompt 只是每次推理的软偏置）
- 所有读取函数在首次调用时确保模板文件存在
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

DATA_DIR = os.path.expanduser("~/.voice-input")
HOTWORDS_MD = os.path.join(DATA_DIR, "hotwords.md")
HOTWORDS_LEGACY_TXT = os.path.join(DATA_DIR, "hotwords.txt")
CORRECTIONS_MD = os.path.join(DATA_DIR, "corrections.md")

_ARROW_RE = re.compile(r"^(?:-\s+|[*+]\s+)?(.+?)\s*(?:→|->)\s*(.+?)\s*$")

HOTWORDS_TEMPLATE = """# 热词表 — 每行一个专有名词/术语，注入识别上下文提升命中率。
# 以 # 开头的行是注释。保存后下一段录音立即生效，无需重启。

- Thistelles
"""

CORRECTIONS_TEMPLATE = """# 纠正词典 — 转写完成后按「错误 → 正确」逐条替换（确定性行为）。
# 格式：- 错误写法 → 正确写法
# 以 # 开头的行是注释。保存后下一段录音立即生效。

- 隐形千疑 → 引擎迁移
"""

DATA_DIR_NOTE = "~/.voice-input"


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return f.readlines()


def parse_terms(md_text: str) -> list[str]:
    """从 md 文本提取热词条目：剥掉注释/空行/列表标记。"""
    terms = []
    for line in md_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "→" in s or "->" in s:  # 误放入纠正格式的行跳过
            continue
        s = re.sub(r"^[-*+]\s+", "", s)
        s = re.sub(r"^\d+[.]\s+", "", s)
        s = s.strip()
        if s:
            terms.append(s)
    return terms


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


def load_hotword_terms() -> list[str]:
    _ensure_dir()
    # 幂等迁移：旧 txt 存在且 md 缺失时转换一次
    if os.path.exists(HOTWORDS_LEGACY_TXT) and not os.path.exists(HOTWORDS_MD):
        try:
            legacy = "".join(_read_lines(HOTWORDS_LEGACY_TXT))
            terms = [ln.strip() for ln in legacy.splitlines()]
            body = "\n".join(ln for ln in terms if ln and not ln.startswith("#"))
            with open(HOTWORDS_MD, "w", encoding="utf-8") as f:
                f.write(
                    "# （由 hotwords.txt 自动迁移）\n\n"
                    + (body + "\n" if body else "")
                )
            logger.info("vocab: migrated hotwords.txt -> hotwords.md")
        except Exception:
            logger.exception("vocab: migration failed")
    if not os.path.exists(HOTWORDS_MD):
        with open(HOTWORDS_MD, "w", encoding="utf-8") as f:
            f.write(HOTWORDS_TEMPLATE)
    try:
        return parse_terms("".join(_read_lines(HOTWORDS_MD)))
    except Exception:
        logger.exception("vocab: read failed")
        return []


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


def apply_corrections(text: str, pairs: list[tuple[str, str]]) -> str:
    for wrong, right in pairs:
        text = text.replace(wrong, right)
    return text


def reveal(path: str):
    import subprocess

    subprocess.Popen(["open", "-t", path])


def reveal_hotwords():
    ensure_hotword_file()
    reveal(HOTWORDS_MD)


def reveal_corrections():
    ensure_correction_file()
    reveal(CORRECTIONS_MD)


def ensure_hotword_file():
    _ensure_dir()
    if os.path.exists(HOTWORDS_MD):
        return
    if os.path.exists(HOTWORDS_LEGACY_TXT):
        load_hotword_terms()  # 触发迁移
        if os.path.exists(HOTWORDS_MD):
            return
    with open(HOTWORDS_MD, "w", encoding="utf-8") as f:
        f.write(HOTWORDS_TEMPLATE)


def ensure_correction_file():
    _ensure_dir()
    if not os.path.exists(CORRECTIONS_MD):
        with open(CORRECTIONS_MD, "w", encoding="utf-8") as f:
            f.write(CORRECTIONS_TEMPLATE)
