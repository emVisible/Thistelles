<div align="center">

# 🎙️ Thistelles

**Menu-bar voice input for macOS — hold to talk, text lands instantly. 100% local inference.**

[![Release](https://img.shields.io/github/v/release/emVisible/Thistelles)](https://github.com/emVisible/Thistelles/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-macOS%2012%2B%20Apple%20Silicon-black)
[![Tests](https://img.shields.io/github/actions/workflow/status/emVisible/Thistelles/test.yml?label=tests)](https://github.com/emVisible/Thistelles/actions/workflows/test.yml)

[中文](README.md) · English

</div>

---

**Thistelles** is a macOS menu-bar voice input tool: hit a global hotkey to record,
release when done, and the transcript lands exactly where you want it — inserted
at your cursor or copied to the clipboard.

All inference runs locally on Apple Metal GPU. Your voice never leaves your machine.
The core experience of Wispr Flow / Superwhisper, free and open source.

[中文文档](README.md) contains the most up-to-date details.

## ✨ Features

- ⚡ **Metal GPU accelerated** — MLX engine + large-v3-turbo, sub-second short clips
- 🔒 **100% local inference** — works offline, zero audio upload
- 🎯 **Insert at cursor** — simulated paste after transcription; clipboard-only mode also available
- ⌨️ **Two key modes** — click-to-toggle or push-to-talk
- 🌏 **Mixed zh/en speech** — automatic language detection, traditional→simplified conversion
- 🏷️ **Custom dictionary** — deterministic `wrong → right` correction + proper-noun context bias; improves with use
- 📌 **History** — search, pin favorites (immune to trimming), one-click export
- 🛟 **Fault-tolerant** — model downloads fail over to a mirror endpoint automatically

## 🚀 Quick Start

```bash
git clone https://github.com/emVisible/Thistelles.git
cd Thistelles
bash guide.sh install          # all-in-one: build, install & launch from /Applications
```

> Requires [uv](https://docs.astral.sh/uv/) and macOS 12+ (Apple Silicon).
> Grant **Microphone** and **Accessibility** permissions when prompted.

### Usage

1. Press `⌘⇧'` anywhere to start recording (release to stop in push-to-talk mode)
2. Press again to stop — text lands per your output mode
3. One menu button, three states: idle「Start Recording」→ recording「Stop
   Recording」→「Transcribing… Click to Cancel」(click while transcribing to abort;
   to discard a clip, stop and cancel immediately)

### Settings

Click **Settings** in the menu to open a native panel — every change applies
immediately: hotkey recorder with live feedback (plus a one-click
**restore default**), key mode, output mode, recognition language, display
language (中文 / English), precision, model quantization, microphone device,
history cap, idle unload, silence auto-stop, a **launch-at-login** checkbox,
and an accessibility status row with a direct link to authorize. The
**Custom Dictionary** link at the bottom opens `corrections.md` — see the
guide in the [Chinese README](README.md).

### Common Commands

```bash
bash guide.sh install          # upgrade / reinstall: just run it again
bash guide.sh models            # download models only (~1.8GB)
bash guide.sh uninstall         # uninstall (interactive: keep or wipe models & data)
bash guide.sh                   # interactive menu (doubles as status overview)
```

## ⚙️ Configuration

`~/.voice-input/config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `hotkey` | `cmd+shift+'` | Global hotkey (re-record via Settings) |
| `language` | `zh-CN` | Recognition language: `auto` detect, or zh-CN / en-US / ja / ko / de / fr / es / ru / pt |
| `ui_language` | `zh-CN` | Display (UI) language: `zh-CN` / `en-US`, switch in Settings |
| `mode` | `base` | `base` fast / `max` accurate (large-v3-turbo) |
| `output_mode` | `paste` | `paste` insert at cursor / `both` insert + keep clipboard / `clipboard` copy only |
| `hotkey_mode` | `toggle` | `toggle` click / `ptt` hold-to-talk |
| `auto_stop_silence_s` | `0` | Auto-stop after N seconds of silence, 0 = off |
| `max_record_s` | `600` | Max single-recording duration, 0 = unlimited |
| `model_idle_unload_min` | `30` | Unload model weights & Metal buffers after N idle minutes (~1.6GB saved); auto-reloads on next transcription; 0 = keep resident |
| `model_variant` | `fp16` | Max model quantization: `fp16` (1.6GB) / `q4` (~800MB, slight accuracy cost) |
| `input_device_name` | empty (system default) | Input device name substring; or pick via Settings → Microphone |
| `history_limit` | `100` | History cap (pinned entries are never trimmed) |
| `paste_delay_ms` | `120` | Delay before simulated paste so the target app settles (rarely tuned) |
| `context_prompt` | `true` | Inject the tail of the previous transcript as recognition context (advanced) |

### Custom Dictionary

Dictionary file: `~/.voice-input/corrections.md` (the **Custom Dictionary**
button in Settings opens it). Changes apply on the very next recording — no
restart needed. Two entry types:

```markdown
# 1. Correction: deterministic replacement after transcription
#    (format: - wrong → right; no inline comments — the whole line counts)
- 隐形千疑 → 引擎迁移
- wrong -> right

# 2. Noun bias: bare terms injected into recognition context
- Thistelles
- MLX
```

Tips:

- **Add a correction every time a word comes out wrong** — deterministic
  replacement beats any prompt trick
- The right side of a correction also feeds noun bias automatically; proper
  nouns with no fixed mis-transcription can be bare entries
- Replacements run top to bottom — order longer fixes before shorter ones
- Lines starting with `#` are comments; legacy `hotwords.txt` / `hotwords.md`
  files are no longer read — merge them into the dictionary manually

## 🔧 Troubleshooting

Run the self-diagnosis first — most known failure classes (version drift,
missing deps, authorization state, hotkey registration) report their own fix:

```bash
bash guide.sh doctor
```

<details>
<summary><b>Hotkey not responding</b></summary>

System Settings → Privacy & Security → **Accessibility** → make sure
**Thistelles** is enabled. The app requests authorization ~3 seconds after
launch; you can also use the status row at the bottom of Settings.
Permissions bind to the .app once granted. **No restart needed after
granting** — the app retries hotkey registration every 8 seconds and
self-heals once authorized.
</details>

<details>
<summary><b>Prompt says「Python3.12」or the app is missing from the Accessibility list</b></summary>

Older builds referenced an interpreter outside the bundle via symlink, which
mis-attributed identity. Fixed: the interpreter now ships inside the bundle,
so prompts and the list show **Thistelles** with its icon. Stale python3.12
entries can be removed manually.
</details>

<details>
<summary><b>Terminal prints「launched from /Applications/Thistelles.app」</b></summary>

Normal forwarding: running `thistelles` from a shell has no app identity, so
it relaunches via the installed bundle automatically. For CLI debugging:
`THISTELLES_FORCE_CLI=1 thistelles`.
</details>

<details>
<summary><b>How to verify I'm running the fixed build</b></summary>

Check the first line of `~/.voice-input/app.log` for `build=xxxxxxxx` — it
changes after each reinstall; together with `hotkey: ready` it means the
latest code is active.
</details>

<details>
<summary><b>Model download fails / restricted network</b></summary>

Built-in redundancy: if the default HuggingFace endpoint fails, `hf-mirror.com`
is used automatically. Manual prefetch: `bash guide.sh models`. Behind a proxy?
Set `HF_ENDPOINT=https://hf-mirror.com` and `HF_HUB_DISABLE_XET=1`, then relaunch.
</details>

## ⚠️ Known Limitations

- Apple Silicon (M1+) only — MLX single engine, no CPU fallback
- MLX runs as one blocking pass; cancelling mid-run takes effect after completion
- First use of Max mode downloads ~1.6GB of model weights

## 🗺️ Roadmap

- [ ] LLM post-processing pipeline (punctuation & filler cleanup, OpenAI-compatible BYOK)
- [x] ~~Microphone device selection~~ — supported via Settings → Microphone
- [ ] Live transcription preview
- [ ] MCP server for AI agent integration

## 🤝 Contributing

Issues and PRs welcome!

```bash
python3 -m unittest discover -s tests    # make tests green before submitting
bash guide.sh install                    # refresh local install from source (idempotent)
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Key design decisions are summarized in the [CHANGELOG.md](CHANGELOG.md) appendix.

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) — the speech recognition model
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon acceleration
- [rumps](https://github.com/jaredks/rumps) — macOS menu-bar framework
- [Quartz Event Services](https://developer.apple.com/documentation/coregraphics/quartz_event_services) — global hotkeys & key capture

## 📄 License

[MIT](LICENSE) © Thistelles Contributors
