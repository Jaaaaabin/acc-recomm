"""
Centralized logging configuration.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict

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
        level: Logging level
    
    Returns:
        Configured logger
    """
    logger: logging.Logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Console handler
    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format: logging.Formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_dir_result: Union[Path, Dict[str, Path]] = get_path('logs', 'root')
        
        # Ensure we got a Path, not a Dict
        if isinstance(log_dir_result, dict):
            raise ValueError("Expected a single path for 'logs.root', but got a dictionary")
        
        log_dir: Path = log_dir_result
        log_path: Path = log_dir / log_file
        
        # Ensure log directory exists
        log_dir.mkdir(parents=True, exist_ok=True)
        
        file_handler: logging.FileHandler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(level)
        file_format: logging.Formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger