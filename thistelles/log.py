import logging
import os
import sys
import threading

DATA_DIR = os.path.expanduser("~/.voice-input")
LOG_FILE = os.path.join(DATA_DIR, "app.log")

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

        fh = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        _logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        _logger.addHandler(ch)

        return _logger
