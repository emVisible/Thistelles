import os
import threading

from . import log as log_mod

logger = log_mod.get_logger()

MODE_MODEL_MAP = {
    "base": "base",
    "max": "large-v3",
}

_whisper_models: dict[str, object] = {}
_whisper_lock = threading.Lock()
_opencc_converter = None
_opencc_lock = threading.Lock()
_loading_event = threading.Event()


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


def resolve_model(mode: str) -> str:
    return MODE_MODEL_MAP.get(mode, "base")


def max_available() -> bool:
    cache = os.path.expanduser(
        "~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3"
    )
    if not os.path.isdir(cache):
        return False
    snapshots = os.path.join(cache, "snapshots")
    if not os.path.isdir(snapshots):
        return False
    for entry in os.listdir(snapshots):
        snapshot_dir = os.path.join(snapshots, entry)
        if os.path.isdir(snapshot_dir):
            if any(f.endswith(".bin") for f in os.listdir(snapshot_dir)):
                return True
    return False


def _load_model(model_size: str) -> object | None:
    global _whisper_models
    model = _whisper_models.get(model_size)
    if model is not None:
        return model
    logger.info("engine: importing faster-whisper …")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    with _whisper_lock:
        model = _whisper_models.get(model_size)
        if model is not None:
            return model
        try:
            logger.info("model: loading %s (int8) …", model_size)
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _whisper_models[model_size] = model
            logger.info("model: %s loaded ✓", model_size)
            return model
        except Exception:
            logger.error("model: failed to load %s", model_size)
            return None


def preload(mode: str):
    model_size = resolve_model(mode)
    logger.info("preload: starting %s …", model_size)
    _load_model(model_size)
    _loading_event.set()
    logger.info("preload: ready")


def is_loading() -> bool:
    return not _loading_event.is_set() and not any(
        m is not None for m in _whisper_models.values()
    )


def transcribe(
    wav_path: str,
    language: str = "zh-CN",
    mode: str = "base",
    beam_size: int = 5,
) -> tuple[str | None, str | None]:
    model_size = resolve_model(mode)
    logger.debug("transcribe: model=%s lang=%s beam=%d", model_size, language, beam_size)
    result, err = _transcribe_whisper(wav_path, language, model_size, beam_size)
    if result is None and err:
        return None, err
    if result is None:
        return None, None
    text = result.strip()
    if not text:
        return None, None
    if language == "zh-CN":
        text = _to_simplified(text)
    return text, None


def _transcribe_whisper(
    wav_path: str,
    language: str,
    model_size: str,
    beam_size: int,
) -> tuple[str | None, str | None]:
    model = _load_model(model_size)
    if model is None:
        return None, "model_error"

    try:
        segments, info = model.transcribe(
            wav_path,
            language=language.split("-")[0],
            beam_size=beam_size,
        )
        logger.debug("transcribe: duration=%.1fs", info.duration if info else 0)
        text = "".join(seg.text for seg in segments).strip()
        logger.debug("transcribe: result=%s", text[:60])
        return text, None
    except Exception:
        logger.error("transcribe: inference failed", exc_info=True)
        return None, "inference_error"
