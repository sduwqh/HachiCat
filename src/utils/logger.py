"""Structured logging for HaChiCat.

References:
- Sakura: app/core/debug_log.py — GUI-accessible debug log with auto-redaction
- We keep it simple: console + file, with consistent formatting.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = "hachicat",
    level: int = logging.DEBUG,
    log_dir: Path | None = None,
) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        name: Logger name.
        level: Log level for console output.
        log_dir: Directory for log files. If None, no file logging.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # Prevent duplicate handlers on re-init
    if logger.handlers:
        return logger

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler (rotating, max 5MB × 3 files)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "hachicat.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "hachicat") -> logging.Logger:
    """Get a logger by name. Falls back to root hachicat logger."""
    return logging.getLogger(name)
