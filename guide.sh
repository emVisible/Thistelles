#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP="Thistelles"
MODEL_CACHE="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3"

# ── helpers ──────────────────────────────────────────────────────────

_uv()      { command -v uv &>/dev/null; }
_python()  { uv python find &>/dev/null; }
_model()   { [[ -d "$MODEL_CACHE/snapshots" ]] && ls "$MODEL_CACHE/snapshots"/*/*.bin &>/dev/null; }
_model_sz(){ du -sh "$MODEL_CACHE" 2>/dev/null | cut -f1 || echo "?"; }
_model_rm(){ echo "  Removing large-v3 model cache..."; rm -rf "$MODEL_CACHE"; echo "  Done."; }
_ensure_uv(){ _uv || { echo "Error: 'uv' not found. Install: https://docs.astral.sh/uv/#installation"; exit 1; }; }
_ensure_py(){ _python || { echo "Error: Python 3.10+ not found."; exit 1; }; }
_model_status() { _model && echo "cached ($(_model_sz))" || echo "not cached"; }

# ── build & install ──────────────────────────────────────────────────

_build_and_install() {
    _ensure_uv; _ensure_py
    echo "==> Building $APP"
    uv build 2>&1
    echo "==> Installing $APP"
    local wheel; wheel=$(ls dist/thistelles-*.whl 2>/dev/null | head -1)
    [[ -n "$wheel" ]] || { echo "Error: no wheel in dist/"; exit 1; }
    uv tool install --reinstall "$wheel" 2>&1
}

_do_prefetch() {
    local py; py=$(uv tool dir)/thistelles/bin/python3
    [[ -f "$py" ]] || { echo "Error: $APP not installed. Run 'install' first."; exit 1; }
    echo "==> Downloading large-v3 model (~3GB)..."
    "$py" -c "
from huggingface_hub import snapshot_download
import sys
sys.stdout.flush()
snapshot_download('Systran/faster-whisper-large-v3')
print('  large-v3 model cached.')
" 2>&1
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
        echo "  large-v3 model already $(_model_status). Skipping."
    elif $force; then
        echo ""; _do_prefetch; echo ""; echo "  Full install complete."
    elif [[ -t 0 ]]; then
        echo ""
        read -rp "  Download large-v3 model for Max mode? (≈3GB) [y/N] " yn
        case "$yn" in y|Y|yes|Yes) echo ""; _do_prefetch ;; esac
    fi
}

cmd_uninstall() {
    _ensure_uv
    echo "==> Uninstalling $APP"
    uv tool uninstall thistelles 2>&1 || echo "  (not installed)"
    echo "==> Cleaning up build artifacts"
    rm -rf dist/ build/ *.egg-info thistelles.egg-info/
    echo "  Done."
    echo ""

    if [[ "${1:-}" == "--purge" || "${1:-}" == "-p" ]]; then
        _model && { _model_rm; echo ""; } || true
    elif [[ -t 0 ]] && _model; then
        local sz; sz=$(_model_sz)
        read -rp "  Remove cached large-v3 model (${sz})? [y/N] " yn
        case "$yn" in y|Y|yes|Yes) echo ""; _model_rm ;; esac
        echo ""
    fi
    echo "  $APP has been uninstalled."
}

cmd_reinstall() {
    local had_model=false; _model && had_model=true

    cmd_uninstall "${1:-}"
    echo ""

    if $had_model; then
        # model survived uninstall — skip download prompt
        cmd_install
    else
        cmd_install "${1:-}"
    fi
}

cmd_prefetch() {
    _ensure_uv
    if _model; then
        echo "  large-v3 model already $(_model_status). Nothing to do."
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
    echo "  large-v3 model: $(_model_status)"
    echo ""
    echo "  Config:  ~/.voice-input/config.json"
    echo "  History: ~/.voice-input/history.json"
    echo "  Cache:   ~/.cache/huggingface/hub/"
}

cmd_help() {
    echo "Usage: bash guide.sh <command> [options]"
    echo ""
    echo "Commands:"
    echo "  install       Build and install (interactive prompt for large model)"
    echo "  install --full  Install with large-v3 model download"
    echo "  uninstall     Remove app (interactive prompt for model cache)"
    echo "  uninstall --purge Remove app and model cache"
    echo "  reinstall     Reinstall app (preserves model cache)"
    echo "  reinstall --full Reinstall with large-v3 model download"
    echo "  prefetch      Download large-v3 model only"
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
        printf "  %-30s %s\n" "large-v3:" "$(_model_status)"
        echo ""
        echo "  1) Install       - with optional large model"
        echo "  2) Full Install  - with large model download"
        echo "  3) Reinstall     - refresh app (preserves model cache)"
        echo "  4) Reinstall*    - refresh app with model download"
        echo "  5) Uninstall     - remove app"
        echo "  6) Prefetch      - download large model only"
        echo "  7) Status        - show installation state"
        echo "  8) Help"
        echo "  9) Quit"
        echo ""
        read -rp "  Choose [1-9] or q: " ch
        echo ""
        case "$ch" in
            1) cmd_install   ;;
            2) cmd_full      ;;
            3) cmd_reinstall ;;
            4) cmd_reinstall --full ;;
            5) cmd_uninstall ;;
            6) cmd_prefetch  ;;
            7) cmd_status    ;;
            8) cmd_help      ;;
            q|Q|9) echo "  Bye."; exit 0 ;;
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
    status|s)       cmd_status ;;
    help|h|--help)  cmd_help ;;
    *)              interactive_menu ;;
esac
