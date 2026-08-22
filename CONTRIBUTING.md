# 贡献指南 / Contributing

感谢关注 Thistelles！以下是开发流程速览。

## 开发环境

- macOS 12+（Apple Silicon 推荐，MLX 引擎需要）
- [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/emVisible/Thistelles.git
cd Thistelles
bash guide.sh install      # 构建并安装到 uv tool 环境
```

## 从源码运行

```bash
uv venv && uv pip install -e .
uv run python -m thistelles
```

> PyAudio 需要 PortAudio 头文件：`brew install portaudio`

## 测试

提交前必须跑通测试（CI 会自动执行）：

```bash
bash guide.sh test         # 或: python -m unittest discover -s tests -v
```

测试只覆盖纯逻辑模块（config / history / inserter 门禁 / transcriber 调度），
GUI 层暂无自动化——涉及菜单行为的改动请手动验收。

## 源码改动后的本地刷新

```bash
bash guide.sh reinstall    # 重装并重启应用
```

注意：运行中的进程加载的是启动时的代码，改完源码必须重装+重启才能生效。

## 提交规范

- 一个 PR 只解决一件事；不顺手重构无关代码
- 行为变更需同步更新 README 配置表与 CHANGELOG.md
- 新增用户可见文案需同时提供 zh-CN 与 en-US 两份

## 设计决策

关键架构取舍记录在 [CHANGELOG.md](CHANGELOG.md) 附录「关键设计决策速览」，提出相关区域改动前建议先阅读。
