# ADR-0001 · 转写引擎选型：MLX（Metal）为主，CTranslate2 兜底

> **状态修订（2026-08-22）**：本决策的"双引擎"部分已被取代——产品确认仅面向
> macOS Apple Silicon，遵循奥卡姆剃刀移除 CT2 兜底，MLX 成为唯一引擎
> （v0.8.0）。max 档使用 large-v3-turbo 的子决策继续有效。
> 保留本文作为历史推理与迁移路径记录。

状态：已采纳（部分被取代） · 日期：2026-08-22

## 背景

macOS 上可选的本地 Whisper 推理引擎：

| 引擎 | 后端 | Apple Silicon 实测 |
|------|------|--------------------|
| faster-whisper (CTranslate2) | CPU int8（无 Metal 支持） | ~0.7x 实时 |
| mlx-whisper | Metal GPU | base 热运行 ~16x 实时；turbo 大幅领先 |
| whisper.cpp | Metal | 与 MLX 相近 |

152 秒录音在 CT2 上需等待约 105 秒，是产品最大的体验瓶颈。

## 决策

1. **默认优先 MLX**（`engine: auto` 时探测可用性），高精度模式映射
   `large-v3-turbo` 而非 full large-v3——听写场景精度几乎持平、速度显著更快。
2. **CT2 保留为兜底**：MLX 导入失败或单次推理异常时自动降级重试一次，
   保证"永远能出结果"。
3. 引擎选择逻辑收敛在 `transcriber.py` 单文件内，公共 API 签名不变
   （依赖倒置：换引擎的改动面趋近于一个模块）。

## 已知代价

- MLX 为整段阻塞推理：转写中途取消只能在完成后丢弃结果
  （CT2 支持段间即时取消）。turbo 后单次转写仅数秒，痛点可接受。
- mlx-whisper 仅实现贪心解码，不支持 beam_size。

## 结果

4.5s 测试音频：CT2 large-v3 14.4s → MLX turbo 1.79s（约 8 倍），
且 turbo 输出标点更完整。

---

## 修订 · 单引擎化（v0.8.0）

**决策**：移除 CT2 兜底与 faster-whisper 依赖，MLX 成为唯一推理路径。

**理由**：
1. 产品本身是 macOS 应用（rumps/PyObjC/CGEvent），不存在跨平台诉求
2. 双引擎在 MLX 正常时零开销，但引入了持续的概念税
   （engine 配置、探测逻辑、双份模型映射、4.5GB 预取）
3. Intel Mac 生态正在退场（macOS 27 移除 Rosetta），VoiceInk 等同类已拒绝 Intel

**接受代价**：
- 失去自动兜底：MLX 运行时失败 = 转写失败（报错通知，不再静默降级）
- 放弃 Intel Mac 支持
- 取消时机退化为完成后丢弃结果（turbo 后单次仅数秒，痛感小）

**收益**：transcriber.py 约 -150 行；prefetch 从 ~4.5GB 降至 ~1.8GB；
安装依赖减少 ctranslate2/faster-whisper/tokenizers 整条链。
