#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP="Thistelles"
APP_BUNDLE="/Applications/Thistelles.app"
DATA_DIR="$HOME/.voice-input"
# 双引擎时代的旧 CT2 large-v3 缓存保留在 purge 列表中，便于一次性释放磁盘
MODEL_CACHES=(
    "$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3"
    "$HOME/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo"
    "$HOME/.cache/huggingface/hub/models--mlx-community--whisper-base-mlx"
)

# ── helpers ──────────────────────────────────────────────────────────

_uv()      { command -v uv &>/dev/null; }
_python()  { uv python find &>/dev/null; }
_ensure_uv(){ _uv || { echo "Error: 'uv' not found. Install: https://docs.astral.sh/uv/#installation"; exit 1; }; }
_ensure_py(){ _python || { echo "Error: Python 3.10+ not found."; exit 1; }; }

_tpython() {
    # 通过已安装的 venv python 查询应用状态；未安装时静默失败
    command -v uv &>/dev/null || return 1
    local p; p="$(uv tool dir)/thistelles/bin/python3" || return 1
    [[ -x "$p" ]] || return 1
    "$p" "$@"
}

# 引擎感知的模型缓存判定：单一真相源在 transcriber 内部
_model() {
    _tpython -c 'import sys
from thistelles.transcriber import max_model_cached as m
sys.exit(0 if m() else 1)' &>/dev/null
}

_model_status(){
    local out
    if out=$(_tpython -c 'from thistelles.transcriber import cache_summary_line
print(cache_summary_line())' 2>/dev/null); then
        echo "$out"
    else
        echo "unknown (app not installed)"
    fi
}

_model_sz(){ du -sch "${MODEL_CACHES[@]}" 2>/dev/null | tail -1 | cut -f1 || echo "?"; }
_model_rm(){ echo "  Removing whisper model caches..."; rm -rf "${MODEL_CACHES[@]}"; echo "  Done."; }

# ── build & install ──────────────────────────────────────────────────

_build_and_install() {
    _ensure_uv; _ensure_py
    echo "==> Building $APP"
    rm -rf dist   # 清掉历史 wheel，防止字母序选中旧版本
    uv build 2>&1
    echo "==> Installing $APP"
    local wheel; wheel=$(ls -t dist/thistelles-*.whl 2>/dev/null | head -1 || true)
    [[ -n "$wheel" ]] || { echo "Error: no wheel in dist/"; exit 1; }
    uv tool install --reinstall "$wheel" 2>&1
}

_do_prefetch() {
    local py; py=$(uv tool dir)/thistelles/bin/python3
    [[ -f "$py" ]] || { echo "Error: $APP not installed. Run 'bash guide.sh install' first."; exit 1; }
    echo "==> Downloading models (base + large-v3-turbo, ~1.8GB)..."
    "$py" -c "
import json
from thistelles.transcriber import prefetch_all
print('  prefetch:', json.dumps(prefetch_all()))
" 2>&1
}

# ── .app bundle ──────────────────────────────────────────────────────

_resolve_path() {
    # 跟随符号链接解析真实路径（macOS 兼容，不依赖 coreutils）
    local p="$1"
    while [[ -L "$p" ]]; do
        local d; d="$(cd "$(dirname "$p")" && pwd)"
        p="$(readlink "$p")"
        [[ "$p" != /* ]] && p="$d/$p"
    done
    echo "$p"
}

_make_app() {
    _ensure_uv
    local pybin; pybin="$(uv tool dir)/thistelles/bin/python3"
    [[ -x "$pybin" ]] || { echo "Error: $APP not installed. Run 'bash guide.sh install' first."; exit 1; }
    local ver; ver=$(thistelles --version 2>/dev/null | awk '{print $2}'); [[ -n "$ver" ]] || ver="0.0.0"

    echo "==> Building $APP_BUNDLE (v$ver)"
    rm -rf "$APP_BUNDLE"
    mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

    # 关键：把解释器「实体拷贝」进包内（而非符号链接——链接会被内核
    # 解析回 uv 目录，TCC 授权弹窗就会显示 Python3.12 + 空白图标）。
    # 拷贝后可执行文件落在 .app 内部，系统弹窗/Dock 显示应用名与图标；
    # 运行时身份仍由 __PYVENV_LAUNCHER__ 定位原 venv 的 site-packages。
    local real_py; real_py="$(_resolve_path "$pybin")"
    cp -f "$real_py" "$APP_BUNDLE/Contents/MacOS/PythonRuntime"
    chmod +x "$APP_BUNDLE/Contents/MacOS/PythonRuntime"

    # 携带其私有动态库（约定 @executable_path/../lib/libpython*.dylib）
    mkdir -p "$APP_BUNDLE/Contents/lib"
    local dep src
    while read -r dep; do
        src="$(dirname "$real_py")/../lib/$(basename "$dep")"
        [[ -f "$src" ]] && cp -f "$src" "$APP_BUNDLE/Contents/lib/"
    done < <(otool -L "$APP_BUNDLE/Contents/MacOS/PythonRuntime" \
             | awk '$1 ~ /^@executable_path\// {print $1}')

    # ── 生成 App 图标 ──
    # 优先级：assets/app_icon.icns > assets/app_icon.png > 由 mic_idle.png 合成。
    # mic_idle 是纯黑镂空模板字形，直接缩放在 Dock/授权弹窗里近乎隐形，
    # 故默认以其为中心合成圆角底板的标准图标。
    local src_icon="thistelles/assets/mic_idle.png"
    local icon_master="$APP_BUNDLE/Contents/Resources/app_icon_master.png"
    local venv_root; venv_root="$(dirname "$(dirname "$pybin")")"

    if [[ -f "assets/app_icon.icns" ]]; then
        cp -f "assets/app_icon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
        echo "==> Using custom app_icon.icns"
        icon_done=true
    elif [[ -f "assets/app_icon.png" ]]; then
        cp -f "assets/app_icon.png" "$icon_master"
        echo "==> Using custom app_icon.png"
    fi

    if [[ ! -f "$icon_master" && "$src_icon" != "" && -f "$src_icon" ]]; then
        __PYVENV_LAUNCHER__="$pybin" VIRTUAL_ENV="$venv_root" \
        ICON_SRC="$(cd "$(dirname "$src_icon")" && pwd)/$(basename "$src_icon")" \
        ICON_OUT="$icon_master" \
        "$APP_BUNDLE/Contents/MacOS/PythonRuntime" - <<'PYGEN' || true
import os
from AppKit import (
    NSImage, NSBitmapImageRep, NSPNGFileType, NSBezierPath, NSColor,
    NSGraphicsContext,
)
from Foundation import NSMakeRect

S = 1024
src = NSImage.alloc().initWithContentsOfFile_(os.environ["ICON_SRC"])

canvas = NSImage.alloc().initWithSize_((S, S))
canvas.lockFocus()
pad = int(S * 0.10); tile = S - 2 * pad
plate = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
    NSMakeRect(pad, pad, tile, tile), int(tile * 0.225), int(tile * 0.225))
NSColor.colorWithCalibratedRed_green_blue_alpha_(0.94, 0.94, 0.96, 1.0).set()
plate.fill()
# 细描边增加层次（浅色模式下的轮廓感）
NSColor.colorWithCalibratedRed_green_blue_alpha_(0.82, 0.82, 0.85, 1.0).set()
plate.setLineWidth_(max(2, S // 340))
plate.stroke()

glyph_side = tile * 0.60
x = pad + (tile - glyph_side) / 2; y = pad + (tile - glyph_side) / 2
src.drawInRect_fromRect_operation_fraction_(
    NSMakeRect(x, y, glyph_side, glyph_side), ((0, 0), (0, 0)),
    getattr(__import__("AppKit"), "NSCompositingOperationSourceOver", 2), 1.0)
canvas.unlockFocus()

rep = NSBitmapImageRep.imageRepWithData_(canvas.TIFFRepresentation())
png = rep.representationUsingType_properties_(NSPNGFileType, None)
png.writeToFile_atomically_(os.environ["ICON_OUT"], True)
print("==> Icon master composed")
PYGEN
        if [[ -f "$icon_master" ]]; then
            local iconset="$APP_BUNDLE/Contents/Resources/AppIcon.iconset"
            mkdir -p "$iconset"
            local s d
            for s in 16 32 128 256 512; do
                d=$((s * 2))
                sips -z "$s" "$s" "$icon_master" --out "$iconset/icon_${s}x${s}.png" >/dev/null 2>&1 || true
                sips -z "$d" "$d" "$icon_master" --out "$iconset/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
            done
            if iconutil -c icns "$iconset" -o "$APP_BUNDLE/Contents/Resources/AppIcon.icns" >/dev/null 2>&1; then
                echo "==> App icon generated"
            else
                echo "==> Warning: iconutil failed, bundle will use default icon"
            fi
            rm -rf "$iconset"
        fi
    fi

    cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>zh-CN</string>
    <key>CFBundleExecutable</key><string>Thistelles</string>
    <key>CFBundleIdentifier</key><string>com.thistelles.app</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>Thistelles</string>
    <key>CFBundleDisplayName</key><string>Thistelles</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleShortVersionString</key><string>$ver</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>LSUIElement</key><true/>
    <key>NSMicrophoneUsageDescription</key><string>语音输入需要使用麦克风录音并在本地转写。</string>
</dict>
</plist>
PLIST

    local venv_root; venv_root="$(dirname "$(dirname "$pybin")")"
    local macos_dir; macos_dir="$APP_BUNDLE/Contents/MacOS"

    cat > "$APP_BUNDLE/Contents/MacOS/Thistelles" <<LAUNCH
#!/bin/bash
# 包内符号链接启动时 CParse 不解析符号链接找 pyvenv.cfg，
# 必须显式指向真实 venv 解释器，否则 site-packages 缺失无法导入
export __PYVENV_LAUNCHER__="$pybin"
export VIRTUAL_ENV="$venv_root"
exec "$macos_dir/PythonRuntime" -c 'import sys; from thistelles.cli import entry; sys.exit(entry())' "\$@"
LAUNCH
    chmod +x "$APP_BUNDLE/Contents/MacOS/Thistelles"

    # ── ad-hoc 深签名：赋予 bundle 稳定代码身份 ──
    # 未签名的 bundle 在新版 macOS 上无法被 TCC 稳定归属（授权弹窗显示
    # 解释器名、辅助功能授权不生效）。ad-hoc 签名以 Info.plist 的
    # CFBundleIdentifier 作为身份锚点；重装会更换 cdhash，故每次安装后
    # 首次启动需重新授权一次（应用会主动弹窗引导）。
    if command -v codesign &>/dev/null; then
        local cs_log; cs_log="$(mktemp)"
        # 内层解释器必须携带与 bundle 一致的标识符——TCC 按发起调用的
        # 可执行文件身份匹配授权，--deep 自动派生的随机标识会导致
        # 「列表已勾选却始终未授权」的身份漂移
        if ! codesign --force --sign - --identifier com.thistelles.app \
                "$APP_BUNDLE/Contents/MacOS/PythonRuntime" 2>"$cs_log"; then
            echo "==> Warning: inner codesign failed:"; sed 's/^/    /' "$cs_log"
        fi
        if codesign --force --sign - "$APP_BUNDLE" 2>>"$cs_log"; then
            echo "==> Bundle ad-hoc signed (id=com.thistelles.app)"
        else
            echo "==> Warning: codesign failed:"
            sed 's/^/    /' "$cs_log"
        fi
        rm -f "$cs_log"
    fi

    # kill old instance (含包内形态), relaunch fresh (-n 防止 open 仅激活旧实例)
    _kill_app
    open -n "$APP_BUNDLE"
    echo "==> $APP launched from $APP_BUNDLE"
}

_login_item() {
    osascript -e "tell application \"System Events\" to get the name of every login item" 2>/dev/null | grep -qw "$APP"
}

_login_disable() {
    osascript -e "tell application \"System Events\" to delete login item \"$APP\"" >/dev/null
}

_kill_app() {
    # 同时覆盖 CLI(venv 解释器) 与 .app(包内拷贝) 两种进程形态
    pkill -f "/uv/tools/thistelles" 2>/dev/null || true
    pkill -f "Thistelles.app/Contents/MacOS/PythonRuntime" 2>/dev/null || true
    sleep 1
}

# ── TUI 选择器 ───────────────────────────────────────────────────────
# 现代交互惯例（create-vite / bun init 风格）：
# ↑↓ 移动高亮，Enter 仅用于最终确认，Esc/q 返回上一级。

SELECT_RESULT=""

_select() {
    # 用法: _select "提示" "选项A" "选项B" ...
    # 层级导航（主流 TUI 惯例）：
    #   ↑↓/j/k 移动高亮；→/l/Enter = 确认或进入子级；←/h/Esc/q = 返回上级。
    # 确认时选中项写入全局 SELECT_RESULT；返回时为空串。
    local prompt="$1"; shift
    local -a opts=("$@")
    local n=${#opts[@]}
    local idx=0 key seq drawn=0 i confirmed=0
    SELECT_RESULT=""
    trap 'tput cnorm 2>/dev/null || true' EXIT INT TERM
    printf '%s\n' "$prompt"
    tput civis 2>/dev/null || true
    while true; do
        ((drawn)) && printf '\033[%dA' "$n"
        for ((i = 0; i < n; i++)); do
            if ((i == idx)); then
                printf '  \033[1;36m❯ %s\033[0m\033[K\n' "${opts[$i]}"
            else
                printf '    %s\033[K\n' "${opts[$i]}"
            fi
        done
        drawn=1
        key=""
        if ! IFS= read -rsn1 key; then
            break                    # EOF/读错误：视为返回，绝不误确认
        fi
        if [[ "$key" == $'\x1b' ]]; then
            seq=""
            # -t 1：箭头序列立即到达不受影响；仅单独按 Esc/h 时最多等 1s
            if IFS= read -rsn2 -t 1 seq; then
                case "$seq" in
                    "[A") idx=$(( (idx - 1 + n) % n )) ;;
                    "[B") idx=$(( (idx + 1) % n )) ;;
                    "[C") confirmed=1; break ;;   # → 确认 / 进入
                    "[D") break ;;                # ← 返回上级
                    *) : ;;                       # 其它序列（如 Shift+Tab）忽略
                esac
            else
                break                             # 单独 Esc = 返回
            fi
        elif [[ -z "$key" ]]; then
            confirmed=1                           # Enter = 确认 / 进入
            break
        elif [[ "$key" == "l" ]]; then
            confirmed=1; break                    # vim l = 右
        elif [[ "$key" == "h" ]]; then
            break                                 # vim h = 左
        elif [[ "$key" == "j" ]]; then
            idx=$(( (idx + 1) % n ))
        elif [[ "$key" == "k" ]]; then
            idx=$(( (idx - 1 + n) % n ))
        elif [[ "$key" == "q" || "$key" == "Q" ]]; then
            break
        fi
    done
    tput cnorm 2>/dev/null || true
    # 关键：退出前擦除本菜单块（提示行 + 选项行），光标回到提示行起始处。
    # 上级重绘或下级菜单都从同一位置「原位替换」，任何层级切换都不残留。
    printf '\033[%dA\033[J' "$((n + 1))"
    if ((confirmed)); then
        SELECT_RESULT="${opts[$idx]}"
    fi
}

# ── commands（对外仅 4 个；开机自启在应用「设置」窗口开关）──────────

cmd_install() {
    # 一站式入口：构建 wheel → 安装到 uv tool 环境 → 生成 .app 并启动。
    # 幂等：重复执行即「重装/升级」——覆盖旧版、保留模型缓存，
    # 应用重启后加载新代码。取代旧版 install / reinstall / app / full。
    _build_and_install

    if _model; then
        echo ""
        echo "  Max-mode models already cached."
    elif [[ -t 0 ]]; then
        local yn
        echo ""
        read -rp "  Download transcription models for Max mode (~1.8GB)? [y/N] " yn
        case "$yn" in y|Y|yes|Yes) echo ""; _do_prefetch ;; esac
    fi

    echo ""
    _make_app
}

_uninstall_common() {
    _ensure_uv
    _kill_app
    echo "==> Uninstalling $APP"
    uv tool uninstall thistelles 2>&1 || echo "  (not installed)"

    if _login_item; then
        _login_disable 2>/dev/null || true
        echo "==> Removed login item"
    fi
    if [[ -d "$APP_BUNDLE" ]]; then
        rm -rf "$APP_BUNDLE"
        echo "==> Removed $APP_BUNDLE"
    fi

    echo "==> Cleaning up build artifacts"
    rm -rf dist/ build/ *.egg-info thistelles.egg-info/
}

_uninstall_half() {
    # 半卸载：移除应用本体；模型缓存与个人数据保留，重装即恢复
    _uninstall_common
    echo ""
    echo "  $APP has been uninstalled (models & data kept)."
}

_uninstall_full() {
    # 全卸载：应用 + 模型缓存 + ~/.voice-input（配置/历史/自定义词典）
    _uninstall_common
    if _model; then _model_rm; fi
    if [[ -d "$DATA_DIR" ]]; then
        rm -rf "$DATA_DIR"
        echo "==> Removed $DATA_DIR (config / history / dictionary)"
    fi
    echo ""
    echo "  $APP has been fully removed."
}

uninstall_flow() {
    while true; do
        _select "卸载范围 · ↑↓ 移动 · →/Enter 确认 · ←/Esc 返回:" \
            "半卸载 · 移除应用；保留模型缓存与个人数据（重装即恢复）" \
            "全卸载 · 连同模型缓存与个人数据一并清除（不可恢复）"
        case "$SELECT_RESULT" in
            半*)
                _uninstall_half
                echo ""
                read -rp "按 Enter 返回…" _
                return ;;
            全*)
                _select "全卸载将永久删除：应用、模型缓存 (~/.cache/huggingface)、${DATA_DIR}（配置 / 历史 / 自定义词典）。确认？ · →/Enter 确认 · ←/Esc 取消" \
                    "确认，全部清除" \
                    "取消"
                if [[ "$SELECT_RESULT" == 确认* ]]; then
                    _uninstall_full
                    echo ""
                    read -rp "按 Enter 返回…" _
                fi
                return ;;
            "")
                return ;;   # ← / Esc 返回上级
        esac
    done
}

menu_install() {
    # 安装与升级子菜单：功能解耦，避免顶级入口一步触发长流程
    while true; do
        _select "安装与升级 · ↑↓ 移动 · →/Enter 执行 · ←/Esc 返回:" \
            "安装 / 升级并启动 · 构建安装 + /Applications 启动（幂等重装）" \
            "仅下载转写模型 · base + turbo 约 1.8GB（已缓存自动跳过）"
        case "$SELECT_RESULT" in
            安装*)
                cmd_install
                echo ""
                read -rp "按 Enter 返回…" _
                ;;
            仅下载*)
                cmd_models
                echo ""
                read -rp "按 Enter 返回…" _
                ;;
            "")
                return ;;   # ← / Esc 返回主菜单
        esac
    done
}

cmd_models() {
    _ensure_uv
    if _model; then
        echo "  Max-mode models already cached. Nothing to do."
        return
    fi
    _do_prefetch
    echo ""
    echo "  Max mode is ready."
}

# ── 自检：把历史事故逐类变成体检项 ───────────────────────────────────

_stamp_pkg() {  # $1 = thistelles 包目录 → 核心模块内容指纹
    for f in main.py hotkeys.py settings_window.py vocab.py; do
        [[ -f "$1/$f" ]] && shasum "$1/$f" | awk '{print $1}'
    done | shasum | cut -c1-8
}

cmd_doctor() {
    local fail=0 warn=0
    local inst_site
    inst_site="$("$(uv tool dir)/thistelles/bin/python3" \
        -c "import sysconfig, os; print(os.path.join(sysconfig.get_paths()['purelib'], 'thistelles'))" 2>/dev/null)"

    echo "== Thistelles 体检 =="
    local n_proc=""  # 应用进程在 open 后需 1-2 秒完成 exec 链，稍候再查

    # 1) 安装与版本漂移
    local ver; ver="$(thistelles --version 2>/dev/null || true)"
    if [[ -n "$ver" ]]; then
        echo "✅ 已安装 $ver"
    else
        echo "❌ 未安装 —— bash guide.sh install"; fail=1
    fi
    local s_src s_inst
    s_src="$(_stamp_pkg "$PWD/thistelles")"
    s_inst="$(_stamp_pkg "$inst_site" 2>/dev/null || echo '?')"
    if [[ "$s_src" == "$s_inst" ]]; then
        echo "✅ 运行代码与源码一致 ($s_inst)"
    else
        echo "❌ 源码有改动未重装（安装=${s_inst} 源码=${s_src}）—— bash guide.sh install"; fail=1
    fi

    # 2) 进程与单实例
    # macOS pgrep 无 -c 旗标：以 pgrep -fl | grep -c 计数（排除 resource_tracker）
    local n_proc=0 i
    for i in 1 2 3; do
        n_proc=$(( \
            $(pgrep -fl "Thistelles.app/Contents/MacOS/PythonRuntime" 2>/dev/null | grep -vc resource_tracker || true) + \
            $(pgrep -fl "/uv/tools/thistelles/bin/python3.*thistelles.cli" 2>/dev/null | grep -vc resource_tracker || true) ))
        ((n_proc > 0)) && break
        sleep 2
    done
    case "$n_proc" in
        1) echo "✅ 进程运行中" ;;
        0) echo "⚠️  应用未运行 —— open -n /Applications/Thistelles.app"; warn=$((warn+1)) ;;
        *) echo "❌ 存在 $n_proc 个实例（多实例会争抢单例锁）—— pkill -f thistelles 后重启"; fail=1 ;;
    esac

    # 3) 依赖完整性（历史事故：ApplicationServices 缺失导致授权检查静默失效）
    local dep_missing=""
    for m in ApplicationServices Quartz rumps pyaudio; do
        _tpython -c "import $m" 2>/dev/null || dep_missing="$dep_missing $m"
    done
    if [[ -z "$dep_missing" ]]; then
        echo "✅ 关键依赖完整"
    else
        echo "❌ 缺依赖:$dep_missing —— bash guide.sh install 重装"; fail=1
    fi

    # 4) 辅助功能授权（热键与插入的生命线）
    local ax; ax="$(_tpython -c 'from thistelles import inserter as i; print("True" if i.accessibility_trusted(prompt=False) else "False")' 2>/dev/null)"
    if [[ "$ax" == "True" ]]; then
        echo "✅ 辅助功能已授权"
    else
        echo "❌ 辅助功能未授权 —— 系统设置→隐私与安全性→辅助功能 勾选 Thistelles"; fail=1
    fi

    # 5) 热键注册状态（取最近日志判定）
    local hk_line; hk_line="$(grep "hotkey:" ~/.voice-input/app.log 2>/dev/null | tail -3 | grep -E "ready|updated|failed" | tail -1)"
    if [[ "$hk_line" == *"ready"* || "$hk_line" == *"updated"* ]]; then
        echo "✅ 热键已注册：${hk_line#*[INFO] }"
    elif [[ "$hk_line" == *"failed"* ]]; then
        echo "❌ 热键注册失败（见上一条辅助功能检查；授权后 8 秒内自动重试）"; fail=1
    else
        echo "⚠️  热键状态未知（日志不足）"; warn=$((warn+1))
    fi

    # 6) 麦克风权限
    local mic; mic="$(_tpython -c '
from AVFoundation import AVMediaTypeAudio, AVCaptureDevice
s = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
print({0:"not_determined",1:"granted",2:"denied",3:"restricted"}.get(s,"unknown"))
' 2>/dev/null || echo unknown)"
    case "$mic" in
        granted)   echo "✅ 麦克风已授权" ;;
        not_determined) echo "⚠️  麦克风尚未请求（首次录音时系统会询问）"; warn=$((warn+1)) ;;
        *)         echo "⚠️  麦克风权限=${mic}（依赖或状态异常，不影响已授权用户）"; warn=$((warn+1)) ;;
    esac

    # 7) bundle 身份与图标声明
    if [[ -d "$APP_BUNDLE" ]]; then
        local ident; ident="$(codesign -dv "$APP_BUNDLE" 2>&1 | awk '/^Identifier=/ {sub(/^Identifier=/,""); print}')"
        if [[ "$ident" == "com.thistelles.app" ]]; then
            echo "✅ bundle 身份正确 ($ident)"
        else
            echo "❌ bundle 身份异常（${ident}）—— 重跑 bash guide.sh install"; fail=1
        fi
        if grep -q CFBundleIconFile "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null; then
            echo "✅ 图标声明存在"
        else
            echo "❌ Info.plist 缺少 CFBundleIconFile —— 重跑 install"; fail=1
        fi
    else
        echo "⚠️  未安装 .app（CLI 模式无应用身份）—— bash guide.sh install"; warn=$((warn+1))
    fi

    echo ""
    if ((fail)); then
        echo "结论：$fail 项需处理 ❌${warn:+，$warn 项提醒 ⚠️}"
        return 1
    fi
    echo "结论：核心链路健康 ✓${warn:+（$warn 项提醒）}"
}

# ── help / menu ──────────────────────────────────────────────────────

usage() {
    cat <<EOF
$APP — macOS menu-bar voice input

用法: bash guide.sh <命令>

  install     一站式安装：
                1) 构建 wheel 并安装到 uv tool 环境（uv tool install --reinstall）
                2) 生成 /Applications/Thistelles.app 并启动
              幂等——重复执行即「重装 / 升级」：自动覆盖旧版、保留模型缓存，
              应用重启后加载新代码。改完源码跑一次即可，无需其它命令。
              终端下交互询问是否下载转写模型（已缓存自动跳过）。
              开机自启在应用「设置」窗口中开关。
  uninstall   卸载，交互区分两档（↑↓ 选择）：
                半卸载 — 移除应用，保留模型缓存与 ~/.voice-input 个人数据
                全卸载 — 额外清除模型缓存与个人数据（需二次确认，不可恢复）
              非交互环境（管道/脚本调用）默认执行半卸载。
  models      仅预下载转写模型（base + large-v3-turbo 约 1.8GB，已缓存自动跳过）。
  doctor      系统自检：版本漂移/进程/依赖/辅助功能/热键注册/麦克风/bundle 身份。

直接运行 bash guide.sh 进入交互菜单：
  ↑↓/j/k 移动 · →/l/Enter 进入或执行 · ←/h/Esc 返回上级（主层级为退出）。
开发与测试命令见 CONTRIBUTING.md。
EOF
}

interactive_menu() {
    if ! [[ -t 0 ]]; then usage; exit 0; fi  # 非交互环境直接打印用法，避免 read 挂死
    # 备用屏幕缓冲区（同 fzf/htop）：菜单只在备用屏内重绘，
    # 层级切换不残留、不堆叠，退出后原终端内容完整还原
    printf '\033[?1049h'
    trap 'tput cnorm 2>/dev/null || true; printf "\033[?1049l"' EXIT INT TERM
    local run=1
    while ((run)); do
        printf '\033[H\033[J'   # 每轮从屏幕顶部清起重绘，杜绝任何残留
        echo "== $APP =="
        printf "  %-14s %s\n" "thistelles:" "$(thistelles --version 2>/dev/null || echo 'not installed')"
        printf "  %-14s %s\n" "models:" "$(_model_status)"
        printf "  %-14s %s\n" "app bundle:" "$( [[ -d "$APP_BUNDLE" ]] && echo "$APP_BUNDLE" || echo 'not installed')"
        printf "  %-14s %s\n" "launch at login:" "$( _login_item && echo enabled || echo disabled )"
        echo ""
        _select "↑↓ 移动 · →/Enter 进入 · ←/Esc 退出:" \
            "安装与升级" \
            "卸载" \
            "查看用法" \
            "退出"
        case "$SELECT_RESULT" in
            安装*) menu_install ;;
            卸载*) uninstall_flow ;;
            查看*)
                usage
                echo ""
                read -rp "按 Enter 返回…" _ ;;
            ""|退出)
                run=0 ;;   # 主层级没有更上级：← / Esc / 退出 即结束
        esac
    done
    tput cnorm 2>/dev/null || true
    printf '\033[?1049l'    # 先还原终端，再在主屏显示告别语
    trap - EXIT INT TERM
    echo "  Bye."
}

# ── dispatch ─────────────────────────────────────────────────────────

case "${1:-}" in
    install|i|reinstall|r) cmd_install ;;   # reinstall 为旧称：install 幂等即重装
    uninstall|u|remove)
        if [[ -t 0 ]]; then
            uninstall_flow
        else
            _uninstall_half   # 脚本/管道场景安全默认：半卸载
            echo "  (非交互环境默认半卸载；终端运行 bash guide.sh 可选择全卸载)"
        fi ;;
    models|m|prefetch|p) cmd_models ;;      # prefetch 为旧称，兼容保留
    doctor|d)            cmd_doctor ;;
    help|h|--help|-h)    usage ;;
    "")                  interactive_menu ;;
    *)
        echo "未知命令: $1 （运行 bash guide.sh 查看可用命令）" >&2
        exit 2 ;;
esac
