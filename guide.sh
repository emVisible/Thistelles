#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP="Thistelles"
APP_BUNDLE="/Applications/Thistelles.app"
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
    [[ -f "$py" ]] || { echo "Error: $APP not installed. Run 'install' first."; exit 1; }
    echo "==> Downloading models (base + large-v3-turbo, ~1.8GB)..."
    "$py" -c "
import json
from thistelles.transcriber import prefetch_all
print('  prefetch:', json.dumps(prefetch_all()))
" 2>&1
}

# ── .app bundle ──────────────────────────────────────────────────────

_make_app() {
    _ensure_uv
    local pybin; pybin="$(uv tool dir)/thistelles/bin/python3"
    local shim; shim="$(uv tool dir)/thistelles/bin/thistelles"
    [[ -x "$pybin" ]] || { echo "Error: $APP not installed. Run 'install' first."; exit 1; }
    local ver; ver=$(thistelles --version 2>/dev/null | awk '{print $2}'); [[ -n "$ver" ]] || ver="0.0.0"

    echo "==> Building $APP_BUNDLE (v$ver)"
    rm -rf "$APP_BUNDLE"
    mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

    # 关键：把 venv python 以「包内符号链接」形式暴露，
    # 使运行进程的可执行路径落在 .app 内部 ——
    # 这样 NSBundle.mainBundle 才能解析出应用身份，
    # UNUserNotificationCenter（系统通知）与 TCC 授权才能绑定成功。
    ln -sf "$pybin" "$APP_BUNDLE/Contents/MacOS/PythonRuntime"

    # ── 生成 App 图标（源：麦克风模板 PNG，多尺寸合成 icns）──
    local src_icon="thistelles/assets/mic_idle.png"
    if [[ -f "$src_icon" ]]; then
        local iconset="$APP_BUNDLE/Contents/Resources/AppIcon.iconset"
        mkdir -p "$iconset"
        local s d
        for s in 16 32 128 256 512; do
            d=$((s * 2))
            sips -z "$s" "$s" "$src_icon" --out "$iconset/icon_${s}x${s}.png" >/dev/null 2>&1 || true
            sips -z "$d" "$d" "$src_icon" --out "$iconset/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
        done
        if iconutil -c icns "$iconset" -o "$APP_BUNDLE/Contents/Resources/AppIcon.icns" >/dev/null 2>&1; then
            echo "==> App icon generated"
        else
            echo "==> Warning: iconutil failed, bundle will use default icon"
        fi
        rm -rf "$iconset"
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

    # kill old instance, relaunch fresh
    pkill -f "/uv/tools/thistelles" 2>/dev/null || true
    sleep 1
    open "$APP_BUNDLE"
    echo "==> $APP launched from $APP_BUNDLE"
}

_login_item() {
    osascript -e "tell application \"System Events\" to get the name of every login item" 2>/dev/null | grep -qw "$APP"
}

cmd_app() {
    _make_app
}

cmd_login() {
    case "${1:-status}" in
        enable)
            [[ -d "$APP_BUNDLE" ]] || _make_app
            if _login_item; then
                echo "  Login item already enabled."
            else
                osascript -e "tell application \"System Events\" to make login item at end with properties {path:\"$APP_BUNDLE\", hidden:true}" >/dev/null \
                    && echo "  Launch at login: enabled." \
                    || { echo "Error: failed to add login item."; exit 1; }
            fi
            ;;
        disable)
            if _login_item; then
                osascript -e "tell application \"System Events\" to delete login item \"$APP\"" >/dev/null \
                    && echo "  Launch at login: disabled."
            else
                echo "  Login item not set."
            fi
            ;;
        *)
            _login_item && echo "  Launch at login: enabled." || echo "  Launch at login: disabled."
            [[ -d "$APP_BUNDLE" ]] || echo "  App bundle not installed ($APP_BUNDLE)."
            ;;
    esac
}

cmd_test() {
    _ensure_uv
    local py; py="$(uv tool dir)/thistelles/bin/python3"
    [[ -x "$py" ]] || { echo "Error: $APP not installed. Run 'install' first."; exit 1; }
    echo "==> Running tests (source tree, venv deps)"
    PYTHONPATH="$PWD" "$py" -m unittest discover -s tests -v
}

# ── commands ─────────────────────────────────────────────────────────

cmd_install() {
    _build_and_install
    echo ""
    echo "  Done! Run: thistelles"
    echo "  Grant microphone & Accessibility permissions when prompted."
    echo "  Accessibility: System Settings -> Privacy & Security -> Accessibility -> add Terminal"

    local force=false
    [[ "${1:-}" == "--full" || "${1:-}" == "-f" ]] && force=true

    if _model; then
        echo ""
        echo "  Max-mode models already cached. Skipping."
    elif $force; then
        echo ""; _do_prefetch; echo ""; echo "  Full install complete."
    elif [[ -t 0 ]]; then
        echo ""
        read -rp "  Download transcription models for Max mode (~1.8GB)? [y/N] " yn
        case "$yn" in y|Y|yes|Yes) echo ""; _do_prefetch ;; esac
    fi
}

_kill_app() {
    pkill -f "/uv/tools/thistelles" 2>/dev/null || true
    sleep 1
}

cmd_uninstall() {
    local keep_app=false purge=false
    local a
    for a in "$@"; do
        case "$a" in
            --keep-app) keep_app=true ;;
            --purge|-p) purge=true ;;
        esac
    done

    _ensure_uv
    _kill_app
    echo "==> Uninstalling $APP"
    uv tool uninstall thistelles 2>&1 || echo "  (not installed)"

    if ! $keep_app; then
        if _login_item; then
            osascript -e "tell application \"System Events\" to delete login item \"$APP\"" >/dev/null 2>&1 || true
            echo "==> Removed login item"
        fi
        if [[ -d "$APP_BUNDLE" ]]; then
            rm -rf "$APP_BUNDLE"
            echo "==> Removed $APP_BUNDLE"
        fi
    fi

    echo "==> Cleaning up build artifacts"
    rm -rf dist/ build/ *.egg-info thistelles.egg-info/
    echo "  Done."
    echo ""

    if $purge; then
        _model && { _model_rm; echo ""; } || true
    elif [[ -t 0 ]] && _model && ! $keep_app; then
        local sz; sz=$(_model_sz)
        read -rp "  Remove cached whisper models (${sz})? [y/N] " yn
        case "$yn" in y|Y|yes|Yes) echo ""; _model_rm ;; esac
        echo ""
    fi
    echo "  $APP has been uninstalled."
}

cmd_reinstall() {
    local had_model=false had_app=false had_login=false
    _model && had_model=true
    [[ -d "$APP_BUNDLE" ]] && had_app=true
    _login_item && had_login=true

    # --keep-app：卸载阶段保留 .app 与登录项，构建失败时旧版仍可用
    cmd_uninstall --reinstall --keep-app
    echo ""

    if $had_model; then
        cmd_install
    elif [[ "${1:-}" == "--full" || "${1:-}" == "-f" ]]; then
        cmd_install --full
    else
        cmd_install
    fi

    if $had_app; then
        echo "==> Refreshing $APP_BUNDLE"
        _make_app >/dev/null 2>&1 || true
    fi
    if $had_login; then
        cmd_login enable >/dev/null 2>&1 || true
        echo "==> Login item restored"
    fi
    echo "  Done! Accessibility permissions may need to be re-granted."
    echo "  System Settings -> Privacy & Security -> Accessibility -> add Terminal"
}

cmd_prefetch() {
    _ensure_uv
    if _model; then
        echo "  Max-mode models already cached. Nothing to do."
        return
    fi
    _do_prefetch
    echo ""
    echo "  Max mode is ready."
}

cmd_full() {
    cmd_install --full
}

cmd_status() {
    local ver; ver=$(thistelles --version 2>/dev/null || echo "not installed")
    echo "== $APP Status =="
    echo ""
    echo "  thistelles:     $ver"
    echo "  models:         $(_model_status)"
    echo "  app bundle:     $([[ -d "$APP_BUNDLE" ]] && echo "$APP_BUNDLE" || echo "not installed")"
    printf "  launch at login: "; _login_item && echo "enabled" || echo "disabled"
    echo ""
    echo "  Config:  ~/.voice-input/config.json"
    echo "  History: ~/.voice-input/history.json"
    echo "  Cache:   ~/.cache/huggingface/hub/"
}

cmd_help() {
    echo "Usage: bash guide.sh <command> [options]"
    echo ""
    echo "Commands:"
    echo "  install       Build and install (interactive prompt for models)"
    echo "  install --full  Install with model download"
    echo "  uninstall     Remove app (interactive prompt for model cache)"
    echo "  uninstall --purge Remove app and model cache"
    echo "  reinstall     Reinstall app (preserves model cache)"
    echo "  reinstall --full Reinstall with model download"
    echo "  prefetch      Download transcription models (~1.8GB)"
    echo "  app           Install /Applications/Thistelles.app and launch"
    echo "  login [enable|disable|status]  Manage launch at login (default: enable)"
    echo "  test          Run test suite against the source tree"
    echo "  status        Show installation status"
    echo "  help          Show this message"
}

# ── interactive menu ─────────────────────────────────────────────────

interactive_menu() {
    while true; do
        echo ""
        echo "== $APP Guide =="
        echo ""
        printf "  %-30s %s\n" "thistelles:" "$(thistelles --version 2>/dev/null || echo 'not installed')"
        printf "  %-30s %s\n" "models:" "$(_model_status)"
        echo ""
        echo "  1) Install       - with optional model download"
        echo "  2) Full Install  - with model download"
        echo "  3) Reinstall     - refresh app (preserves model cache)"
        echo "  4) Reinstall*    - refresh app with model download"
        echo "  5) Uninstall     - remove app"
        echo "  6) Prefetch      - download models (~1.8GB)"
        echo "  7) App           - install /Applications/Thistelles.app"
        echo "  8) Login         - toggle launch at login"
        echo "  9) Status        - show installation state"
        echo "  0) Help"
        echo "  q) Quit"
        echo ""
        read -rp "  Choose [1-9, 0, q]: " ch
        echo ""
        case "$ch" in
            1) cmd_install   ;;
            2) cmd_full      ;;
            3) cmd_reinstall ;;
            4) cmd_reinstall --full ;;
            5) cmd_uninstall ;;
            6) cmd_prefetch  ;;
            7) cmd_app       ;;
            8) if _login_item; then cmd_login disable; else cmd_login enable; fi ;;
            9) cmd_status    ;;
            0|h|H) cmd_help  ;;
            q|Q) echo "  Bye."; exit 0 ;;
            *) echo "  Invalid choice."; continue ;;
        esac
        echo ""; read -rp "  Press Enter to continue..."
    done
}

# ── dispatch ─────────────────────────────────────────────────────────

case "${1:-}" in
    install|i)      shift; cmd_install "${1:-}" ;;
    uninstall|u)    shift; cmd_uninstall "${1:-}" ;;
    reinstall|r)    shift; cmd_reinstall "${1:-}" ;;
    full|f)         cmd_full ;;
    prefetch|p)     cmd_prefetch ;;
    app|a)          cmd_app ;;
    login|l)        shift; cmd_login "${1:-enable}" ;;
    test|t)         cmd_test ;;
    status|s)       cmd_status ;;
    help|h|--help)  cmd_help ;;
    *)              interactive_menu ;;
esac
