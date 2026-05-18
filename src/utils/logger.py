"""结构化日志"""

import logging
import logging.handlers
from pathlib import Path

from src.config import LOG_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", encoding="utf-8",
        maxBytes=5 * 1024 * 1024, backupCount=3,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def get_crash_logger() -> logging.Logger:
    """Dedicated crash logger — writes unhandled exceptions to crash.log."""
    logger = logging.getLogger("crash")
    if logger.handlers:
        return logger

    logger.setLevel(logging.ERROR)

    fmt = logging.Formatter(
        "%(asctime)s [CRASH] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(LOG_DIR / "crash.log", encoding="utf-8")
    fh.setLevel(logging.ERROR)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
