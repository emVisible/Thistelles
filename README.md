# Thistelles

macOS 菜单栏语音输入 — `⌘⇧I` 录音转文字，直达剪贴板。本地转录，无云端依赖。

## Prerequisites

- macOS 12+
- [uv](https://docs.astral.sh/uv/#installation) (Python 包管理器)

## Install

```bash
git clone <repo-url> && cd thistelles
bash guide.sh                # 交互菜单
# 或直接:
bash guide.sh install               # 安装软件
bash guide.sh install --full        # 安装 + 预下载高精度模型
bash guide.sh reinstall             # 重装（保留模型缓存）
bash guide.sh reinstall --full      # 重装 + 重新下载模型
bash guide.sh prefetch              # 已安装后单独下载高精度模型
bash guide.sh uninstall             # 卸载
bash guide.sh uninstall --purge     # 卸载 + 清理 large-v3 缓存
bash guide.sh status                # 查看安装状态
```

安装后运行 `thistelles` 启动（仅图标，无菜单栏文字）。

## Usage

- `⌘⇧I` — 开始/停止录音，转写结果自动复制到剪贴板
- 菜单栏图标可切换语言（中文/English）、精度模式、历史上限
- 历史记录在菜单顶层（`Toggle` 下方），可直接点击复制

## Precision Modes

| Mode | Model | Size | Speed |
|------|-------|------|-------|
| Base (default) | whisper-base | ~74MB | Fast |
| Max | large-v3 | ~3GB | Slow, higher accuracy |

Max 模型首次使用自动下载。可以从菜单栏或 `~/.voice-input/config.json` 切换。

## Config

`~/.voice-input/config.json`:

| key | default | description |
|-----|---------|-------------|
| `hotkey` | `cmd+shift+i` | 全局快捷键 |
| `language` | `zh-CN` | 识别语言: `zh-CN` / `en-US` |
| `history_limit` | `100` | 历史记录上限 |
| `waveform_width` | `280` | 波纹宽度 |
| `waveform_height` | `36` | 波纹高度 |
| `waveform_y` | `bottom` | 波纹位置: `bottom` / `top` / 像素值 |
| `mode` | `base` | 精度模式: `base` / `max` |

## Logs

调试日志位于 `~/.voice-input/app.log`。

## Permissions

- **麦克风** — 首次录音自动请求
- **辅助功能** — 设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal
