"""Logging setup: daily-rotating single log file in a logs/ folder, 7-day retention."""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.getenv("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
LOG_FILE = os.getenv("LOG_FILE", os.path.join(LOGS_DIR, "app.log"))
LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_initialized = False


def init_logging() -> logging.Logger:
    """Configure root + uvicorn loggers to write to one rotating file and stderr."""
    global _initialized
    if _initialized:
        return logging.getLogger("app")
    _initialized = True

    os.makedirs(LOGS_DIR, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    root.handlers[:] = [file_handler, console_handler]

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers[:] = [file_handler, console_handler]
        logger.propagate = False

    logger = logging.getLogger("app")
    logger.info(
        "Logging initialized (file=%s, rotation=midnight, retention=7 days, level=%s)",
        LOG_FILE,
        logging.getLevelName(LOG_LEVEL),
    )
    return logger