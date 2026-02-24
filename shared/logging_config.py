"""Shared logging configuration for dashboard and woody."""

import logging
import sys
from pathlib import Path
from typing import Optional

_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    service: str = "app",
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console: bool = True,
) -> Path:
    """
    Configure logging to file and optionally console.
    Returns the path to the log file.
    """
    root = Path(__file__).resolve().parent.parent
    if log_dir is None:
        log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{service}.log"

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Ensure approval-related loggers are at INFO (visible in docker logs)
    for name in ("shared.chat", "shared.approval_service", "woody.app.approvals", "woody.app.agent"):
        logging.getLogger(name).setLevel(level)

    # Suppress noisy googleapiclient message (file_cache needs oauth2client<4.0; we use google-auth)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

    return log_file
