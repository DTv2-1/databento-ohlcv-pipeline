"""
Logging configuration using loguru
Provides structured logging with rotation and retention
"""

from loguru import logger
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    log_dir: str = "logs",
    level: str = "INFO",
    rotation: str = "00:00",
    retention_days: int = 7,
    console: bool = True
) -> logger:
    """
    Setup logger with file and console handlers
    
    Args:
        log_dir: Directory for log files
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        rotation: When to rotate logs (time or size)
        retention_days: How many days to keep logs
        console: Whether to log to console
    
    Returns:
        Configured logger instance
    """
    # Remove default handler
    logger.remove()
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Console handler (if enabled)
    if console:
        logger.add(
            sys.stdout,
            level=level,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True
        )
    
    # File handler - General log
    logger.add(
        f"{log_dir}/pa_{{time:YYYY-MM-DD}}.log",
        rotation=rotation,
        retention=f"{retention_days} days",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True  # Thread-safe
    )
    
    # File handler - Error log
    logger.add(
        f"{log_dir}/pa_errors_{{time:YYYY-MM-DD}}.log",
        rotation=rotation,
        retention=f"{retention_days} days",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        enqueue=True
    )
    
    logger.info(f"Logger initialized - Level: {level}, Log dir: {log_dir}")
    
    return logger


def get_logger():
    """Get the configured logger instance"""
    return logger
