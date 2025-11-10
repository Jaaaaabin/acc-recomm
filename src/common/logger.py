"""
Centralized logging configuration.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict
from logging.handlers import RotatingFileHandler

from .paths import get_path


def get_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)
        log_file: Optional log file name (saved to logs/)
        level: Logging level (default: logging.INFO)

    Returns:
        Configured logger instance.
    """

    logger: logging.Logger = logging.getLogger(name)

    # Prevent multiple handler duplication
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # === Console handler ===
    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # === File handler (optional) ===
    if log_file:
        log_dir_result: Union[Path, Dict[str, Path]] = get_path("logs", "root")

        if isinstance(log_dir_result, dict):
            raise ValueError("Expected a single Path for 'logs.root', but got a dictionary")

        log_dir: Path = log_dir_result
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped file name to avoid overwriting
        timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path: Path = log_dir / f"{timestamp}_{log_file}"

        # Use rotating handler (5 MB per file, keep 5 backups)
        file_handler: RotatingFileHandler = RotatingFileHandler(
            log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_format: logging.Formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    # Add a separator for clarity in logs
    logger.info("=" * 80)
    logger.info("Logger initialized for module: {}".format(name))
    logger.info("=" * 80)

    return logger