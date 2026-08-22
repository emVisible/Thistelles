# ADR-0003 · 分发形态：uv 工具 + 手工 .app bundle，权限身份绑定应用本体

状态：已采纳 · 日期：2026-08-22

## 背景

Python 菜单栏应用在 macOS 的分发有两类坑：

1. **辅助功能权限**：pynput 全局热键与 CGEvent 粘贴都依赖 TCC 辅助功能授权。
   从 Terminal 启动时权限挂在 Terminal 上；`uv tool` 重装会重建 venv，
   曾导致"重装后热键/图标异常"的连环问题。
2. **幽灵进程**：早期 `_kill_app` 用 `pgrep -fx thistelles` 匹配不到真实
   进程（命令行是 `…/python …/thistelles`），旧实例带着旧热键配置长期存活。

## 决策

1. **主分发**：`guide.sh app` 生成手工 `/Applications/Thistelles.app`
   （Info.plist `LSUIElement` + shell 启动器 exec uv tool 环境）——
   权限绑定应用本体一次授权永久有效，无需 py2app 重型打包。
2. **进程管理**：杀进程统一用 `pkill -f "/uv/tools/thistelles"`；
   应用内加 `fcntl.flock` 单实例锁，双保险杜绝多监听器并存。
3. **Release CI** 打 tag 自动构建 wheel 附到 GitHub Release；
   源码安装路径保持 `git clone → bash guide.sh install`。

## 结果

权限一次授权跨重装稳定；单实例锁使重复启动直接退出。
已知取舍：.app 启动器依赖 uv tool 环境存在，卸载 uv tool 后 .app 无法独立运行
（卸载脚本会同步清理 .app 与登录项）。
