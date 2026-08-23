"""Transcription engine: mlx-whisper on Apple Metal GPU.

Single-engine by design (Occam): Thistelles targets macOS on Apple Silicon,
where MLX is strictly the best local option (~8x realtime with large-v3-turbo).
No CPU fallback — requirement is stated plainly in the README.
"""

import os
import threading
import wave

# 运行期静默第三方进度条：模型已缓存时 huggingface_hub 仍做元数据校验，
# 打印「Fetching N files / Download complete / Reconstruction complete」；
# mlx_whisper 每次转写还会输出帧级 tqdm。两者对用户都是噪声。
# setdefault：保留用户显式覆盖的能力；guide.sh 的 models 下载路径
# 由 _prefetch_repo 临时恢复进度条，大流量下载仍有可见反馈。
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import numpy as np

from . import log as log_mod

logger = log_mod.get_logger()

# 决策记录：max 档使用 large-v3-turbo——听写场景精度与 full large-v3 几乎持平，
# 推理速度显著更快；交互式语音输入优先延迟而非极限精度。
MODEL_REPOS = {
    "base": "mlx-community/whisper-base-mlx",
    "max": "mlx-community/whisper-large-v3-turbo",
}

# 量化变体：仅作用于 max 档，repo 名追加后缀（-q4 权重约省一半内存）。
VARIANTS = {"fp16": "", "q4": "-q4"}

_variant = "fp16"


def set_variant(variant: str):
    """设置 max 档模型变体：'fp16'（默认）或 'q4'。启动时调用一次。"""
    global _variant
    _variant = variant if variant in VARIANTS else "fp16"


def resolve_model(mode: str) -> str:
    repo = MODEL_REPOS.get(mode, MODEL_REPOS["base"])
    if mode == "max":
        repo += VARIANTS.get(_variant, "")
    return repo

_models: dict[str, bool] = {}
_lock = threading.Lock()
_opencc_converter = None
_opencc_lock = threading.Lock()
_loading_event = threading.Event()

# 闲置卸载状态：定时器 + 忙碌标记（防止推理中途释放权重导致崩溃）
_idle_timer: threading.Timer | None = None
_idle_minutes: float = 0.0
_busy = False


def _to_simplified(text: str) -> str:
    global _opencc_converter
    try:
        import opencc

        with _opencc_lock:
            if _opencc_converter is None:
                _opencc_converter = opencc.OpenCC("t2s")
            return _opencc_converter.convert(text)
    except ImportError:
        return text

def _hf_cached(repo_id: str) -> bool:
    root = os.path.expanduser("~/.cache/huggingface/hub")
    d = os.path.join(root, "models--" + repo_id.replace("/", "--"), "snapshots")
    if not os.path.isdir(d):
        return False
    for entry in os.listdir(d):
        sd = os.path.join(d, entry)
        if os.path.isdir(sd):
            if any(f.endswith(".safetensors") for f in os.listdir(sd)):
                return True
    return False


def max_model_cached() -> bool:
    """max 档模型是否已缓存（guide.sh 门禁共用）。"""
    return _hf_cached(MODEL_REPOS["max"])


def cache_summary_line() -> str:
    """单行模型缓存状态（guide.sh 交互菜单共用）。"""
    def mark(mode: str) -> str:
        return "✓" if _hf_cached(MODEL_REPOS[mode]) else "✗"

    return f"engine=mlx · base {mark('base')} · turbo(max) {mark('max')}"


def _ensure_mlx(repo_id: str) -> bool:
    """确认依赖可用且权重已就位；缺权重时经双源冗余链下载。"""
    global _idle_timer
    with _lock:
        if _models.get(repo_id):
            if _idle_timer is not None:
                _idle_timer.cancel()
                _idle_timer = None
            return True
        try:
            import mlx_whisper  # noqa: F401
        except Exception:
            logger.exception("engine: mlx-whisper unavailable")
            return False
        if not _hf_cached(repo_id):
            logger.info("engine: %s not cached, downloading …", repo_id)
            if not _prefetch_repo(repo_id):
                return False
        # 权重由 mlx_whisper 首次调用时按需加载；此处仅标记引擎就绪。
        _models[repo_id] = True
        logger.info("engine: mlx ready (%s)", repo_id)
        return True


def preload(mode: str, idle_unload_min: float = 0.0):
    repo = resolve_model(mode)
    logger.info("preload: starting mlx %s …", repo)
    _ensure_mlx(repo)
    _warmup(repo)
    _loading_event.set()
    _schedule_idle_unload(idle_unload_min)
    logger.info("preload: ready")


def _warmup(repo_id: str):
    """静音预热：提前完成 Metal kernel 编译与权重加载，
    让用户第一次真实说话时就是热路径。失败不致命。"""
    try:
        import mlx_whisper
        import numpy as np

        silence = np.zeros(8000, dtype=np.float32)  # 0.5s
        mlx_whisper.transcribe(
            silence,
            path_or_hf_repo=repo_id,
            language="en",
            condition_on_previous_text=False,
            verbose=False,
        )
        logger.info("warmup: metal kernels ready")
    except Exception as e:
        logger.warning("warmup skipped: %s", e)


def _schedule_idle_unload(minutes: float):
    """N 分钟无转写后释放权重与 Metal 缓冲（minutes<=0 关闭）。"""
    global _idle_timer, _idle_minutes
    if minutes <= 0:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        return
    _idle_minutes = minutes
    if _idle_timer is not None:
        _idle_timer.cancel()
    t = threading.Timer(minutes * 60, _unload_model)
    t.daemon = True
    t.start()
    _idle_timer = t
    logger.debug("memory: idle unload scheduled in %.0f min", minutes)


def apply_idle_unload(minutes: float):
    """配置变更入口：取消旧定时器，立即按新值重排闲置卸载。"""
    _schedule_idle_unload(float(minutes or 0))


def _unload_model():
    global _idle_timer
    # 推理进行中不卸载，顺延一个周期再试
    if _busy:
        _schedule_idle_unload(_idle_minutes or 30)
        return
    with _lock:
        _models.clear()
    try:
        from mlx_whisper.transcribe import ModelHolder

        ModelHolder.model = None
        ModelHolder.model_path = None

        def cache_bytes() -> int | None:
            try:
                import mlx.core as mx

                get = getattr(mxm := mx, "get_cache_memory", None) or getattr(
                    getattr(mx, "metal", None), "get_cache_memory", None
                )
                return get() or 0 if get else None
            except Exception:
                return None

        before = cache_bytes()
        try:
            import mlx.core as mx

            clear = getattr(mx, "clear_cache", None) or getattr(
                getattr(mx, "metal", None), "clear_cache", None
            )
            if clear:
                clear()
        except Exception:
            pass
        after = cache_bytes()
        logger.info(
            "memory: model unloaded (metal cache %s -> %s)",
            f"{before/1e6:.0f}MB" if before is not None else "?",
            f"{after/1e6:.0f}MB" if after is not None else "?",
        )
    except Exception:
        logger.debug("memory: mlx holder release skipped", exc_info=True)
    _idle_timer = None


def is_loading() -> bool:
    return not _loading_event.is_set() and not any(_models.values())


_PROGRESS_ENV_KEYS = ("HF_HUB_DISABLE_PROGRESS_BARS", "TQDM_DISABLE")


def _prefetch_repo(repo_id: str) -> bool:
    """双源冗余下载：默认端点失败后自动切换 hf-mirror。

    镜像无法代理 Xet CAS 存储，故镜像路径强制 HF_HUB_DISABLE_XET=1；
    用子进程隔离镜像环境，避免污染当前进程的全局状态。
    下载期间临时恢复进度条——1.8GB 级流量需要可见反馈。
    """
    saved = {k: os.environ.pop(k, None) for k in _PROGRESS_ENV_KEYS}
    try:
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(repo_id)
            return True
        except Exception as e:
            logger.warning("engine: fetch %s via default endpoint failed: %s", repo_id, e)

        import subprocess
        import sys

        code = (
            "import os; "
            f"os.environ['HF_ENDPOINT']={_MIRROR_ENDPOINT!r}; "
            "os.environ['HF_HUB_DISABLE_XET']='1'; "
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download({repo_id!r})"
        )
        try:
            r = subprocess.run(
                [sys.executable, "-c", code],
                timeout=_PREFETCH_TIMEOUT_S,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                logger.info("engine: fetched %s via mirror ✓", repo_id)
                return True
            logger.error("engine: mirror fetch of %s failed (rc=%s)", repo_id, r.returncode)
            return False
        except Exception:
            logger.exception("engine: mirror fetch of %s crashed", repo_id)
            return False
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


_MIRROR_ENDPOINT = "https://hf-mirror.com"
_PREFETCH_TIMEOUT_S = 3600


def prefetch_all() -> dict[str, bool]:
    """guide.sh 预下载入口：拉齐全部档位模型。"""
    out = {}
    for mode in ("base", "max"):
        out[mode] = _ensure_mlx(resolve_model(mode))
    return out


def transcribe(
    wav_path: str,
    language: str = "zh-CN",
    mode: str = "base",
    initial_prompt: str | None = None,
    cancel_event: threading.Event | None = None,
    idle_unload_min: float = 0.0,
) -> tuple[str | None, str | None]:
    global _busy
    logger.debug(
        "transcribe: lang=%s mode=%s prompt=%s",
        language, mode, bool(initial_prompt),
    )
    _busy = True
    try:
        result, detected, err = _transcribe(
            wav_path, language, mode, initial_prompt, cancel_event
        )
    finally:
        _busy = False
        try:
            _schedule_idle_unload(idle_unload_min)
        except Exception:
            pass
    if err == "cancelled":
        return None, "cancelled"
    if err == "model_error":
        return None, "model_error"
    if err == "inference_error":
        return None, "inference_error"
    if result is None or not result.strip():
        return None, None
    text = result.strip()
    want_simplified = language == "zh-CN" or (
        language == "auto" and detected is not None and str(detected).startswith("zh")
    )
    if want_simplified:
        text = _to_simplified(text)
    return text, None


def _transcribe(
    wav_path: str,
    language: str,
    mode: str,
    initial_prompt: str | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str | None, str | None, str | None]:
    if cancel_event is not None and cancel_event.is_set():
        return None, None, "cancelled"

    repo = resolve_model(mode)
    if not _ensure_mlx(repo):
        return None, None, "model_error"

    lang_param: str | None = None
    if language and language != "auto":
        lang_param = language.split("-")[0]

    # mlx 无 vad_filter：首尾静音裁剪补偿「静音段幻觉」这一已知失败模式。
    source = wav_path
    try:
        audio = _load_wav_array(wav_path)
        if audio is not None:
            source = _trim_silence(audio)
    except Exception:
        source = wav_path

    try:
        import mlx_whisper

        logger.info(
            "transcribe: engine=mlx model=%s lang=%s prompt=%s",
            repo, lang_param or "auto", bool(initial_prompt),
        )
        # 平台契约：mlx 仅贪心解码（beam_size 会抛 NotImplementedError）；
        # 单次阻塞推理——运行中触发的取消只能在完成后生效并丢弃结果。
        result = mlx_whisper.transcribe(
            source,
            path_or_hf_repo=repo,
            language=lang_param,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            verbose=False,
        )
        detected = result.get("language") if isinstance(result, dict) else None
        text = (result.get("text") or "").strip() if isinstance(result, dict) else ""
        if cancel_event is not None and cancel_event.is_set():
            logger.info("transcribe: cancelled (result discarded)")
            return None, None, "cancelled"
        logger.debug("transcribe: result=%s", text[:60])
        return text, detected, None
    except Exception:
        logger.exception("transcribe: mlx inference failed")
        return None, None, "inference_error"


def _load_wav_array(path: str) -> np.ndarray | None:
    with wave.open(path, "rb") as wf:
        if wf.getframerate() != 16000 or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            return None
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


_SILENCE_RMS = 0.01
_TRIM_WIN_S = 0.02
_TRIM_MARGIN_S = 0.15
_MIN_SPEECH_S = 0.2


def _trim_silence(x: np.ndarray) -> np.ndarray:
    rate = 16000
    win = int(_TRIM_WIN_S * rate)
    n = len(x)
    if n < win * 3:
        return x
    rms = np.sqrt(np.convolve(x * x, np.ones(win) / win, mode="same") + 1e-12)
    idx = np.nonzero(rms > _SILENCE_RMS)[0]
    if idx.size == 0:
        return x
    margin = int(_TRIM_MARGIN_S * rate)
    start = max(int(idx[0]) - margin, 0)
    end = min(int(idx[-1]) + margin + win, n)
    if end - start < int(_MIN_SPEECH_S * rate):
        return x
    return x[start:end]
