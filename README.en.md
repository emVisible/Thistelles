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
- 🏷️ **Hotwords** — proper-noun correction + context inheritance from previous clip
- 📌 **History** — search, pin favorites (immune to trimming), one-click export
- 🛟 **Fault-tolerant** — MLX failures auto-fall back to CPU engine; model downloads
  fail over to a mirror endpoint automatically

## 🚀 Quick Start

```bash
git clone https://github.com/emVisible/Thistelles.git
cd Thistelles
bash guide.sh install          # build & install (interactive)
thistelles                     # launch — mic icon appears in the menu bar
```

> Requires [uv](https://docs.astral.sh/uv/) and macOS 12+ (Apple Silicon).
> Grant **Microphone** and **Accessibility** permissions when prompted.

### Common Commands

```bash
bash guide.sh app              # install /Applications/Thistelles.app and launch
bash guide.sh login enable     # launch at login
bash guide.sh test             # run test suite
bash guide.sh prefetch         # pre-download all models (~1.8GB)
```

## ⚙️ Configuration

`~/.voice-input/config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `hotkey` | `cmd+shift+'` | Global hotkey (recordable from menu) |
| `language` | `zh-CN` | `auto` detect, or zh-CN / en-US / ja / ko / de / fr / es / ru / pt (UI text is 中/English) |
| `mode` | `base` | `base` fast / `max` accurate (large-v3-turbo) |
| `output_mode` | `paste` | `paste` insert at cursor / `both` insert + keep clipboard / `clipboard` copy only |
| `hotkey_mode` | `toggle` | `toggle` click / `ptt` hold-to-talk |
| `auto_stop_silence_s` | `0` | Auto-stop after N seconds of silence, 0 = off |
| `max_record_s` | `600` | Max single-recording duration, 0 = unlimited |
| `model_idle_unload_min` | `30` | Unload model weights & Metal buffers after N idle minutes (~1.6GB saved); auto-reloads on next transcription; 0 = keep resident |
| `model_variant` | `fp16` | Max model quantization: `fp16` (1.6GB) / `q4` (~800MB, slight accuracy cost) |
| `input_device_name` | empty (system default) | Input device name substring; or pick via Settings → Microphone |
| `history_limit` | `100` | History cap (pinned entries are never trimmed) |

Hotwords live in `~/.voice-input/hotwords.txt`, one term per line — effective on
the very next recording.

## 🔧 Troubleshooting

<details>
<summary><b>Hotkey not responding</b></summary>

System Settings → Privacy & Security → **Accessibility** → enable Terminal
(or Thistelles.app). Permissions bind to the app bundle once installed.
</details>

<details>
<summary><b>Model download fails / restricted network</b></summary>

Built-in redundancy: if the default HuggingFace endpoint fails, `hf-mirror.com`
is used automatically. Manual prefetch: `bash guide.sh prefetch`. Behind a proxy?
Set `HF_ENDPOINT=https://hf-mirror.com` and `HF_HUB_DISABLE_XET=1`, then relaunch.
</details>

## ⚠️ Known Limitations

- Apple Silicon (M1+) only — MLX single engine, no CPU fallback
- MLX runs as one blocking pass; cancelling mid-run takes effect after completion
- First use of Max mode downloads ~1.6GB of model weights

## 🗺️ Roadmap

- [ ] LLM post-processing pipeline (punctuation & filler cleanup, OpenAI-compatible BYOK)
- [ ] Microphone device selection
- [ ] Live transcription preview
- [ ] MCP server for AI agent integration

## 🤝 Contributing

Issues and PRs welcome!

```bash
bash guide.sh test        # make tests green before submitting
bash guide.sh reinstall   # refresh local install from source changes
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Key design decisions are summarized in the [CHANGELOG.md](CHANGELOG.md) appendix.

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) — the speech recognition model
- [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon acceleration
- [rumps](https://github.com/jaredks/rumps) — macOS menu-bar framework
- [pynput](https://github.com/moses-palmer/pynput) — global keyboard listening

## 📄 License

[MIT](LICENSE) © Thistelles Contributors
