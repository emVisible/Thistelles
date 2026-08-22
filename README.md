<div align="center">

# 🎙️ Thistelles

**macOS 菜单栏语音输入 — 按住说话，文字即达。100% 本地推理，隐私不出设备。**

[![Release](https://img.shields.io/github/v/release/emVisible/Thistelles)](https://github.com/emVisible/Thistelles/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS%2012%2B%20Apple%20Silicon-black)
[![Tests](https://img.shields.io/github/actions/workflow/status/emVisible/Thistelles/test.yml?label=tests)](https://github.com/emVisible/Thistelles/actions/workflows/test.yml)

中文 · [English](README.en.md)

按全局快捷键开始录音 → 松手后本地 Whisper 转写 → 文字自动插入光标处或复制到剪贴板。
全程离线运行，菜单栏常驻一枚麦克风图标，无主窗口打扰。

</div>

---

**Thistelles** 是一款运行在 macOS 菜单栏的语音输入工具：按下全局快捷键开始录音，说完即停，
转写文本按你选择的方式投递——直接插入光标处、或复制到剪贴板。

推理完全在本地完成（Apple Metal GPU 加速），语音数据永不离开你的电脑。
对标 Wispr Flow / Superwhisper 的核心体验，免费开源。

## ✨ 特性

- ⚡ **Metal GPU 加速** — MLX 引擎 + large-v3-turbo，短句转写亚秒级返回
- 🔒 **100% 本地推理** — 无云端依赖，断网可用，语音不上传
- 🎯 **光标处直接插入** — 转写完自动模拟粘贴；也支持纯剪贴板模式
- ⌨️ **双按键模式** — 点击切换（toggle）或按住说话（push-to-talk）
- 🌏 **中英混说** — 自动语种检测，中文自动繁转简
- 🏷️ **热词系统** — 专有名词识别修正 + 上一段上下文继承，越用越准
- 📌 **历史管理** — 搜索过滤、置顶收藏（不受上限裁剪）、一键导出
- 🛟 **容错架构** — MLX 异常自动降级 CPU 引擎；模型下载失败自动切换镜像源

## 🆚 与同类产品对比

| | Thistelles | Wispr Flow | Superwhisper |
|---|---|---|---|
| 价格 | **免费开源 (MIT)** | $15/月 订阅 | $249 买断 |
| 推理位置 | 本地 · Metal GPU | 云端 | 本地 · CPU |
| 完全离线 | ✅ | ❌ | ✅ |
| 光标插入 / 剪贴板 | ✅ 双模式 | 仅插入 | 仅剪贴板 |
| 按住说话 + 点击切换 | ✅ | 部分 | ✅ |
| 中文繁转简 | ✅ | — | 需手动配置 |

## 🚀 快速开始

```bash
git clone https://github.com/emVisible/Thistelles.git
cd Thistelles
bash guide.sh install          # 构建安装（交互式引导）
thistelles                     # 启动，菜单栏出现麦克风图标
```

> 需要 [uv](https://docs.astral.sh/uv/) 与 macOS 12+（Apple Silicon）。
> 首次启动会请求 **麦克风** 与 **辅助功能** 权限，按提示授权即可。

### 常用命令

```bash
bash guide.sh app              # 安装 /Applications/Thistelles.app 并启动
bash guide.sh login enable     # 开机自启
bash guide.sh test             # 运行测试套件
bash guide.sh prefetch         # 预下载全部转写模型（约 1.8GB）
```

### 使用方式

1. 在任意输入框按下 `⌘⇧'`（可在菜单里改）开始录音
2. 说完后再次按下停止——文字按输出方式自动投递
3. 转写中可随时从菜单「配置 → 取消」中断

## ⚙️ 配置

`~/.voice-input/config.json`：

| 键 | 默认值 | 说明 |
|----|--------|------|
| `hotkey` | `cmd+shift+'` | 全局快捷键（可在菜单录制） |
| `language` | `zh-CN` | 识别语言：`auto` 自动检测 / `zh-CN` / `en-US` / 日韩德法西俄葡等（界面文字仅中英） |
| `mode` | `base` | 精度：`base` 快速 / `max` 高精度（large-v3-turbo） |
| `output_mode` | `paste` | 输出：`paste` 插入光标处 / `both` 插入并保留剪贴板 / `clipboard` 仅复制 |
| `hotkey_mode` | `toggle` | 按键模式：`toggle` 点击切换 / `ptt` 按住说话 |
| `auto_stop_silence_s` | `0` | 静音自动停录秒数，`0` 关闭 |
| `max_record_s` | `600` | 单次录音最长秒数，`0` 不限制 |
| `model_idle_unload_min` | `30` | 闲置 N 分钟后释放模型权重与 Metal 缓冲（约省 1.6GB 内存），下次转写自动重载；`0` 常驻 |
| `model_variant` | `fp16` | 高精度模型量化：`fp16`(1.6GB) / `q4`(≈800MB，精度略降，适合 8GB 内存机型) |
| `input_device_name` | 空（系统默认） | 输入设备名子串匹配；也可在菜单「配置 → 麦克风设备」选择 |
| `history_limit` | `100` | 历史记录上限（置顶条目不计入裁剪） |

热词文件 `~/.voice-input/hotwords.txt`：每行一个专有名词，保存后下一段录音立即生效。

## 🔧 故障排查

<details>
<summary><b>快捷键没有反应</b></summary>

系统设置 → 隐私与安全性 → **辅助功能** → 确认 Terminal（或 Thistelles.app）已勾选。
通过 .app 启动时权限绑定应用本体，只需授权一次。
</details>

<details>
<summary><b>模型下载失败 / 网络受限</b></summary>

内置双源冗余：默认 HuggingFace 端点失败会自动切换 `hf-mirror.com` 镜像。
也可手动预取：`bash guide.sh prefetch`。代理用户可设置环境变量
`HF_ENDPOINT=https://hf-mirror.com` 与 `HF_HUB_DISABLE_XET=1` 后重新启动。
</details>

<details>
<summary><b>菜单栏看不到图标</b></summary>

确认进程存活（`pgrep -fl thistelles`）；macOS 菜单栏过满时会折叠图标，
可在系统设置 → 控制中心调整。日志见 `~/.voice-input/app.log`。
</details>

## ⚠️ 已知限制

- 仅支持 Apple Silicon（M1 及以上）—— MLX 单引擎，不提供 CPU 兜底
- MLX 为整段阻塞推理，转写中途取消会在完成后丢弃结果
- 首次使用高精度模式需下载 ~1.6GB 模型

## 🗺️ Roadmap

- [ ] LLM 后处理管线（自动标点/去口水词，OpenAI 兼容协议 BYOK）
- [ ] 录音设备选择（外接麦克风）
- [ ] 转写实时预览
- [ ] MCP server — 让 AI Agent 直接调用听写能力

## 🤝 贡献

欢迎 Issue 与 PR！开发流程：

```bash
bash guide.sh test     # 提交前跑通测试
bash guide.sh reinstall  # 源码改动后刷新本地安装
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。关键设计决策速览见 [CHANGELOG.md](CHANGELOG.md) 附录。

## 🙏 致谢

- [OpenAI Whisper](https://github.com/openai/whisper) — 语音识别模型
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon 加速推理
- [rumps](https://github.com/jaredks/rumps) — macOS 菜单栏应用框架
- [pynput](https://github.com/moses-palmer/pynput) — 全局键盘监听

## 📄 License

[MIT](LICENSE) © Thistelles Contributors
