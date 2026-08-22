Changelog

## [0.10.0] - 2026-08-22

### Added

- Native settings window (设置…): all configuration in one panel with
  immediate effect — hotkey recorder with live symbol feedback (Esc to cancel),
  output/language/precision/quantization/mic device/history/idle-unload/
  silence-stop controls; replaces the nested settings submenus
- Deterministic correction layer (`corrections.md`): `错误 → 正确` pairs applied
  after transcription — the reliable "improves with use" path identified by
  research (Whisper has no input-method-style model learning)
- Hotword file migrated from txt to Markdown (`hotwords.md`), auto-migrated
- Notification authorization requested at startup; delivery failures logged
  instead of silently dropped (root cause of "no popup" reports: the
  UserNotifications framework was never a dependency and requires bundle
  context + granted authorization)
- Recording prevents idle system sleep

### Changed

- Menu slimmed to actions only: 开始/停止、放弃本次录音(动态)、取消转写(动态)、
  历史记录、设置…、退出 — all configuration moved into the settings window
- GitHub link moved from menu into settings window

### Fixed

- Pin-by-number race when a recording completed while the pin dialog was open
  (dialog now carries a snapshot of the list it displayed)

## [0.9.1] - 2026-08-22

### Added

- Wheel metadata now embeds the full README as long description
  (PyPI / `pip show` / GitHub Release page render rich text)

## [0.9.0] - 2026-08-22

### Added

- Microphone device selection: Settings → 麦克风设备 lists input devices;
  selection persists and applies to the next recording (auto-fallback to the
  system default if the chosen device fails or is unplugged)
- Quantized Max model option (`model_variant: q4`, ~800MB vs 1.6GB fp16)
- Recognition languages beyond zh/en: auto, ja, ko, de, fr, es, ru, pt
  (UI text remains 中/English)
- First-run permission guidance: startup check for Accessibility/Microphone
  authorization with a guidance notification
- GitHub repository link in the menu
- History entries show full text as a hover tooltip
- `uv.lock` committed for reproducible builds

### Fixed

- Pin-by-number race: opening the pin dialog snapshots the list, so a recording
  completing while the dialog is open no longer shifts the numbering

### Changed

- Recording prevents idle system sleep (display may still turn off)

## [0.8.1] - 2026-08-22

### Added

- Metal warmup at startup: kernels compile during preload so the first real
  dictation hits the hot path
- Idle model unloading (`model_idle_unload_min`, default 30): releases ~1.6GB
  of weights plus Metal buffer cache after idle time; auto-reloads on next use
- Memory observability: metal cache size logged on unload

## [0.8.0] - 2026-08-22

### Changed (BREAKING)

- **Single-engine architecture**: MLX (Metal GPU) is now the sole transcription
  engine; removed CTranslate2/faster-whisper fallback and its dependency
- Requires Apple Silicon M1+ — Intel Macs are no longer supported
- Max precision mode uses large-v3-turbo (~1.6GB); full large-v3 fully retired
- `engine` config key removed; model prefetch shrunk from ~4.5GB to ~1.8GB

### Removed

- `beam_size` plumbing and ct2-only progress reporting
  (mlx has no incremental segment output)

### Fixed

- Cancel requested before transcription starts now short-circuits immediately

## [0.7.0] - 2026-08-22

### Added

- GitHub productization: bilingual README (中文 / English), CI test workflow,
  tag-triggered release workflow, issue templates, CONTRIBUTING guide,
  and ADR decision records
- Settings menu shows the running version (greyed row)
- CT2 engine reports transcription progress as a percentage in the menu title

### Changed

- Waveform overlay now appears on the display where the mouse is located
- History search filter auto-clears when a new recording lands, so fresh
  entries are never hidden by an active filter

### Fixed

- Search/pin dialogs no longer freeze the whole app while open — osascript
  moved to a background thread with results dispatched through the event queue

## [0.6.0] - 2026-08-22

### Added

- History: keyword search via dialog, filtered menu view with one-click "Show All" reset
- History: pin/unpin by list number — pinned entries float to top and survive the history limit
- History: export all entries to a timestamped text file in ~/Downloads (revealed in Finder)
- App icon: multi-size icns generated from the microphone template asset
- Log rotation: app.log bounded at ~3MB (1MB × active + 2 backups)

### Changed

- History menu now lists entries numbered for pin reference

## [0.5.1] - 2026-08-22

### Added

- Model download dual-source redundancy: automatic hf-mirror fallback when the default
  HuggingFace endpoint fails; mirror path forces Xet off (CAS not proxied)
- `guide.sh prefetch` now fetches both engines' high-accuracy models
- Waveform overlay shows live recording duration
- Optional silence auto-stop (`auto_stop_silence_s`, 0 = off)
- Max recording duration cap (`max_record_s`, default 600s)
- Test suite: `bash guide.sh test` — 30 cases covering config validation,
  output-mode gating, engine dispatch/fallback, cancel short-circuit, silence trim

### Fixed

- Clipboard-only mode no longer pastes into the focused app (CGEvent fired before mode gating)
- Negative numeric config values fall back to defaults instead of clamping to 0
  (which would have silently enabled unlimited recording)

## [0.5.0] - 2026-08-22

### Added

- MLX transcription engine (Apple Metal GPU) alongside CTranslate2, selected by
  `engine` config (`auto` / `mlx` / `ct2`) with automatic fallback on failure
- Max precision mode uses large-v3-turbo under MLX (~8x faster than CPU large-v3)
- Silence trimming before MLX inference compensates its missing VAD filter

### Changed

- Engine swap contained in transcriber module; public API unchanged

### Fixed

- mlx-whisper rejects beam_size (greedy-only decoder) — parameter no longer forwarded
- Corrected MLX model repo ids (`whisper-base-mlx`, not `whisper-base`)

## [0.3.0] - 2026-08-22

### Added

- Transcription quality pack: VAD filter + `condition_on_previous_text=False`
- Push-to-talk mode: hold hotkey to record, release to transcribe
  (`_ComboListener` tracks full-combo press/release edges); switchable in Settings → 按键模式

## [0.2.0] - 2026-08-22

### Added

- Cancel from Settings menu: discards an active recording, or cancels a running
  transcription between whisper segments
- Automatic language detection (`Auto` in language menu) with zh simplified conversion
- Hotwords: editable `~/.voice-input/hotwords.txt` plus zero-maintenance context
  inheritance from the previous transcript's tail (whisper initial_prompt)

### Changed

- Starting a new recording is throttled while the previous clip is still transcribing

### Fixed

- `_start_hotkey` no longer crashes the app when pynput registration fails

## [0.1.x] - 2026-07-24 → 2026-08-22

### Added

- Custom global hotkey capture UI (Settings → 设置快捷键…), default changed to `⌘⇧'`
- Direct text insertion at cursor via synthetic ⌘V (inserter module), three output
  modes: paste / paste-and-keep / clipboard only
- `/Applications/Thistelles.app` bundle (`guide.sh app`) with stable Accessibility identity
- Launch-at-login management (`guide.sh login enable|disable|status`)
- Single-instance lock preventing duplicate hotkey listeners
- Startup exception guards with structured logging

### Fixed

- Ghost-process accumulation across reinstalls (`_kill_app` matches real process cmdline)
- Reinstall flow no longer exits early under `set -euo pipefail`

---

## 附 · 关键设计决策速览

> 原 `docs/adr/` 三篇决策记录的核心结论（v0.9.0 起并入本文档，独立文件已移除）。

### 单引擎 MLX（Metal GPU）

- CTranslate2 在 Apple Silicon 上仅 CPU 执行（无 Metal 支持），152s 录音需等 ~105s；
  MLX + large-v3-turbo 实测快约 8 倍且标点更完整 → 移除 CT2 兜底与 faster-whisper 依赖
- 代价：仅支持 Apple Silicon M1+；转写中途取消在完成后生效；mlx 仅贪心解码

### 输出三分法（paste / both / clipboard）

- 光标插入机制 = 写剪贴板 → 合成 ⌘V → 延迟还原原剪贴板，依赖辅助功能权限
- 粘贴动作必须先经模式门禁再执行；无权限时自动降级 clipboard，不丢文本
- 三种模式的触发矩阵由单元测试锁定（tests/test_inserter.py）

### 分发形态与权限身份

- `guide.sh app` 生成手工 .app bundle：系统授权绑定应用本体，一次授权跨重装有效
- 进程终止以安装路径为锚点匹配；应用内 flock 单实例锁双保险
- 已知取舍：.app 依赖 uv tool 环境存在；卸载脚本会同步清理 .app 与登录项
