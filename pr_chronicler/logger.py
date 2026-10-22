"""
Logging configuration for PR Chronicler.
Logs to both stdout (terminal) and pr_chronicler.log.
"""

import logging
import os
import sys
from typing import Optional

LOG_FILE_PATH = os.environ.get("PR_CHRONICLER_LOG_FILE", "pr_chronicler.log")

def setup_logger(name: str = "pr_chronicler", log_file: str = LOG_FILE_PATH, level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns a logger that outputs to both terminal (stdout)
    and a persistent log file (pr_chronicler.log).
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if logger.handlers:
        return logger

    # Log format
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (Terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (pr_chronicler.log)
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        logger.warning(f"Failed to attach FileHandler for {log_file}: {exc}")

    logger.propagate = False
    return logger

# Default logger instance
logger = setup_logger()
