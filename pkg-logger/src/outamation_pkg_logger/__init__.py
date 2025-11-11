"""
My Org Logging Package
======================

This package provides a pre-configured Loguru instance for all
organization projects.

Usage:
------

Simple (console logging only):
>>> from my_org_logging import logger
>>> logger.info("This is an info message.")
>>> logger.error("This is an error.")

Advanced (console and file logging):
>>> from my_org_logging import logger, setup_logging
>>> setup_logging(log_file_path="my_app.log")
>>> logger.info("This will go to both console and my_app.log")
"""

import functools
import sys
import os
from loguru import logger

logger.remove()

# Give it a level number lower than DEBUG (DEBUG=10)
logger.level("TRACE", no=5, color="<fg #666666>", icon="↪")

LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}"
)

# --- 3. Add a Default Console Handler ---
# This handler is added by default when the package is imported.
# It logs to stderr and its level can be controlled by an env var.
# This ensures that `from my_org_logging import logger` works out of the box.
default_console_level = os.getenv("LOG_LEVEL", "INFO")
logger.add(
    sys.stderr,
    level=default_console_level.upper(),
    format=LOG_FORMAT,
    colorize=True,  # Enable colored output in the console
)


# --- 4. Define the Public Setup Function ---
def setup_logging(
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    log_file_path: str | None = None,
    rotation: str = "10 MB",
    retention: str = "10 days",
):
    """
    Configures the organization-wide logger.

    This function removes all existing handlers and sets up new ones
    based on the provided parameters.

    Args:
        console_level (str): The log level for the console (e.g., "INFO", "DEBUG").
        file_level (str): The log level for the file (e.g., "DEBUG").
        log_file_path (str | None): Path to the log file. If None, file logging is disabled.
        rotation (str): When to rotate the log file (e.g., "10 MB", "12:00", "1 week").
        retention (str): How long to keep old log files (e.g., "10 days", "1 month").
    """
    # Remove all handlers, including the default console one
    logger.remove()

    # Add the new console handler with the specified level
    logger.add(
        sys.stderr,
        level=console_level.upper(),
        format=LOG_FORMAT,
        colorize=True,
    )
    logger.info(f"Console logging enabled at level: {console_level}")

    # Add the file handler IF a path is provided
    if log_file_path:
        try:
            logger.add(
                log_file_path,
                level=file_level.upper(),
                format=LOG_FORMAT,
                rotation=rotation,
                retention=retention,
                compression="zip",  # Compress rotated logs
                enqueue=True,  # Makes logging asynchronous (safe for multiple processes)
            )
            logger.info(
                f"File logging enabled at: {log_file_path} (Level: {file_level})"
            )
        except Exception as e:
            logger.error(f"Failed to set up file logging at {log_file_path}: {e}")
    return logger


# --- NEW TRACE DECORATOR ---
def trace(func):
    """
    A decorator that logs the entry and exit of a function at TRACE level.
    It also logs arguments and the return value.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Format arguments for logging
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)

        logger.trace(f"Entering: {func.__name__}({signature})")

        try:
            result = func(*args, **kwargs)
            logger.trace(f"Exiting: {func.__name__} (result={result!r})")
            return result
        except Exception as e:
            # Re-log the exception at ERROR level and re-raise
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise e

    return wrapper


# --- 5. Define the Public API ---
__all__ = ["logger", "setup_logging", "trace"]
