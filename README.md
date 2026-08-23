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
- 🏷️ **自定义词典** — `错误 → 正确` 确定性纠正 + 专有名词上下文偏好，越用越准
- 📌 **历史管理** — 搜索过滤、置顶收藏（不受上限裁剪）、一键导出
- 🛟 **容错架构** — 模型下载失败自动切换镜像源；权限缺失有自检与引导

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
bash guide.sh install          # 一站式：构建安装 + /Applications 启动（交互式引导）
```

> 需要 [uv](https://docs.astral.sh/uv/) 与 macOS 12+（Apple Silicon）。
> 首次启动会请求 **麦克风** 与 **辅助功能** 权限，按提示授权即可。

### 常用命令

```bash
bash guide.sh install          # 升级 / 重装：重复执行即可（幂等）
bash guide.sh models            # 仅下载转写模型（约 1.8GB）
bash guide.sh uninstall         # 卸载（交互区分：半卸载保留模型与数据 / 全卸载）
bash guide.sh                   # 交互菜单（兼作状态总览）
```

### 使用方式

1. 在任意输入框按下 `⌘⇧'` 开始录音（按住说话模式下松手即停）
2. 说完后再次按下停止——文字按输出方式自动投递
3. 菜单主按钮三态：空闲「开始录音」→ 录音中「停止录音」→「转写中… 点击取消」
   （转写中点击即中断；想丢弃一段录音，停止后立即点击取消即可）

### 设置

菜单点「设置」打开原生设置面板，所有配置**即时生效**：

- **录音快捷键**：点击「重新录制」后按下新组合键，实时回显（Esc 取消）；「恢复默认」一键回到 `⌘⇧'`
- **按键模式**：点击切换 / 按住说话
- **显示语言**：界面文字 中文 / English（与识别语言相互独立）
- **输出方式 / 识别语言 / 精度模式 / 模型量化 / 麦克风设备** 等
- **开机自启**：勾选即写入系统登录项
- **辅助功能状态**：底部实时显示授权状态，未授权时提供「前往授权」直达按钮
- **自定义词典**：面板底部按钮打开 `corrections.md`，维护方式见下节

## ⚙️ 配置

`~/.voice-input/config.json`：

| 键 | 默认值 | 说明 |
|----|--------|------|
| `hotkey` | `cmd+shift+'` | 全局快捷键（在设置窗口「重新录制」） |
| `language` | `zh-CN` | 识别语言：`auto` 自动检测 / `zh-CN` / `en-US` / 日韩德法西俄葡等 |
| `ui_language` | `zh-CN` | 显示语言（界面文字）：`zh-CN` / `en-US`，在设置窗口切换 |
| `mode` | `base` | 精度：`base` 快速 / `max` 高精度（large-v3-turbo） |
| `output_mode` | `paste` | 输出：`paste` 插入光标处 / `both` 插入并保留剪贴板 / `clipboard` 仅复制 |
| `hotkey_mode` | `toggle` | 按键模式：`toggle` 点击切换 / `ptt` 按住说话 |
| `auto_stop_silence_s` | `0` | 静音自动停录秒数，`0` 关闭 |
| `max_record_s` | `600` | 单次录音最长秒数，`0` 不限制 |
| `model_idle_unload_min` | `30` | 闲置 N 分钟后释放模型权重与 Metal 缓冲（约省 1.6GB 内存），下次转写自动重载；`0` 常驻 |
| `model_variant` | `fp16` | 高精度模型量化：`fp16`(1.6GB) / `q4`(≈800MB，精度略降，适合 8GB 内存机型) |
| `input_device_name` | 空（系统默认） | 输入设备名子串匹配；也可在设置窗口「麦克风设备」选择 |
| `history_limit` | `100` | 历史记录上限（置顶条目不计入裁剪） |
| `paste_delay_ms` | `120` | 插入光标前等待目标应用就绪的毫秒数（一般无需调整） |
| `context_prompt` | `true` | 是否把上一段转写尾部作为上下文提示注入识别（进阶） |

## 📖 自定义词典

词典文件 `~/.voice-input/corrections.md`，设置面板底部点「自定义词典」直接打开。
保存后下一段录音立即生效，无需重启。支持两种条目：

```markdown
# 1. 纠正替换：转写完成后逐条确定性替换（格式：- 错误写法 → 正确写法）
#    注意：条目行内不要写注释，整行都会参与替换
- 隐形千疑 → 引擎迁移
- 端道端 -> 端到端

# 2. 名词偏好：裸词条注入识别上下文，提升专有名词命中率
- Thistelles
- MLX
```

维护建议：

- **听到识别错的词就加一条纠正**——这是确定性修正，比任何 prompt 技巧都可靠
- 带箭头条目的「正确写法」会自动作为名词偏好注入上下文；没有固定错法的
  专有名词（人名、产品名）直接写成裸词条即可
- 替换按行序逐条执行，注意先后依赖（如先纠正长词再纠正短词）
- 以 `#` 开头的行是注释；`hotwords.txt` / `hotwords.md` 为旧版遗留，
  已不再读取，可手动把内容合并进词典后删除

## 🔧 故障排查

遇到异常先运行自检，多数历史故障类别（版本漂移、依赖缺失、授权状态、热键注册）会直接给出定位与修复指引：

```bash
bash guide.sh doctor
```

<details>
<summary><b>快捷键没有反应</b></summary>

系统设置 → 隐私与安全性 → **辅助功能** → 确认 **Thistelles** 已勾选。
应用启动约 3 秒后会主动弹出授权请求；也可在设置窗口底部点「前往授权」。
通过 .app 启动时权限绑定应用本体。**勾选后无需重启**——应用每 8 秒自动
重试注册热键，授权完成即生效。
</details>

<details>
<summary><b>模型下载失败 / 网络受限</b></summary>

内置双源冗余：默认 HuggingFace 端点失败会自动切换 `hf-mirror.com` 镜像。
也可手动预取：`bash guide.sh models`。代理用户可设置环境变量
`HF_ENDPOINT=https://hf-mirror.com` 与 `HF_HUB_DISABLE_XET=1` 后重新启动。
</details>

<details>
<summary><b>授权弹窗显示「Python3.12」或辅助功能列表找不到应用</b></summary>

旧版本以符号链接方式引用包外解释器导致身份归属错误，现已修复：
解释器实体随 .app 打包，弹窗与列表均显示 **Thistelles** + 应用图标。
若列表中残留旧的 python3.12 条目可手动移除。
</details>

<details>
<summary><b>终端出现「launched from /Applications/Thistelles.app」提示</b></summary>

这是正常的转发行为：命令行直接运行 `thistelles` 时没有应用身份
（系统弹窗会显示 Python3.12），因此自动转由已安装的 .app 启动。
开发调试确需在终端跑源码进程时：`THISTELLES_FORCE_CLI=1 thistelles`。
</details>

<details>
<summary><b>如何确认运行的是修复后的版本</b></summary>

查看启动日志（`~/.voice-input/app.log`）首行 `build=xxxxxxxx` 指纹，
重装后该指纹应变化；配合 `hotkey: ready` 即为最新代码正常工作。
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
- [x] ~~录音设备选择（外接麦克风）~~ —— 已在设置窗口「麦克风设备」支持
- [ ] 转写实时预览
- [ ] MCP server — 让 AI Agent 直接调用听写能力

## 🤝 贡献

欢迎 Issue 与 PR！开发流程：

```bash
python3 -m unittest discover -s tests   # 提交前跑通测试（或: uv run python -m unittest discover）
bash guide.sh install                   # 源码改动后刷新本地安装（幂等，重复执行即升级）
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。关键设计决策速览见 [CHANGELOG.md](CHANGELOG.md) 附录。

## 🙏 致谢

- [OpenAI Whisper](https://github.com/openai/whisper) — 语音识别模型
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon 加速推理
- [rumps](https://github.com/jaredks/rumps) — macOS 菜单栏应用框架
- [Quartz Event Services](https://developer.apple.com/documentation/coregraphics/quartz_event_services) — 全局热键与按键捕获

## 📄 License

[MIT](LICENSE) © Thistelles Contributors
