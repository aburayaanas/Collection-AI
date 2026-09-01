"""
Centralized Logging Configuration
Provides structured, production-ready logging for the Collection AI batch job.
"""

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from src.core import paths
from src.core.config import settings

# ── Log Rotation Settings ────────────────────────────────────────────
LOG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per file
LOG_BACKUP_COUNT = 5                # keep 5 rotated files (50 MB total max)


def setup_logging() -> logging.Logger:
    """
    Configures application-wide logging with both console and rotating file handlers.
    
    Features:
    - Rotating log files (10 MB max, 5 backups = 50 MB ceiling)
    - Daily file naming with ISO date format
    - Dual output: console + rotating file
    - Debug mode support via settings.DEBUG
    - Professional formatting with timestamps
    
    Returns:
        Configured root logger instance
    """
    
    # Determine log level based on DEBUG setting
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # Writable, fixed location regardless of CWD (a Windows Service's CWD
    # is System32, not the install folder) — see src/core/paths.py.
    log_dir = paths.LOGS_DIR
    
    # Generate daily log file name
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"collection_batch_{today}.log"
    
    # Define professional log format
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # === Console Handler ===
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # === Rotating File Handler (prevents unbounded log growth) ===
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Log the initialization
    root_logger.info("=" * 80)
    root_logger.info(f"Logging initialized: {settings.APP_NAME} v{settings.VERSION}")
    root_logger.info(f"Log Level: {logging.getLevelName(log_level)}")
    root_logger.info(f"Log File: {log_file}")
    root_logger.info(f"Debug Mode: {settings.DEBUG}")
    root_logger.info("=" * 80)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance for a specific module.
    
    Args:
        name: Usually __name__ of the calling module
        
    Returns:
        Logger instance with the specified name
        
    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    return logging.getLogger(name)
