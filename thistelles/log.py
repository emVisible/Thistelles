import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

DATA_DIR = os.path.expanduser("~/.voice-input")
LOG_FILE = os.path.join(DATA_DIR, "app.log")

# 有界化：单文件 1MB，保留 2 个滚动备份，总量上限 ~3MB。
_MAX_LOG_BYTES = 1_000_000
_LOG_BACKUPS = 2

_logger: logging.Logger | None = None
_logger_lock = threading.Lock()


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    with _logger_lock:
        if _logger is not None:
            return _logger

        os.makedirs(DATA_DIR, exist_ok=True)

        _logger = logging.getLogger("thistelles")
        _logger.setLevel(logging.DEBUG)
        _logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )

        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUPS,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        _logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        _logger.addHandler(ch)

        return _logger
