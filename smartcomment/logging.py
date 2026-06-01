"""Centralized logging configuration for smartcomment using `loguru`."""

import sys
from loguru import logger


_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>smartcomment</cyan>:<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


# For first-time initialization, set the log level to WARNING.
# Note that we need to remove the default handler first to avoid duplicate logging.
logger.remove()
logger.add(sys.stderr, level="WARNING", format=_LOG_FORMAT)


def setup_logger(
    level: str = "WARNING",
    filepath: str | None = None,
    *,
    rotation: str | int | None = None,
    retention: str | int | None = None,
    compression: str | None = None,
    format: str | None = None,
    colorize: bool | None = None,
) -> None:
    """Reset the logger with the given level and optional file sink.

    All existing sinks are removed first, then a ``stderr`` sink is added at the
    requested level.  If ``filepath`` is provided, an additional file sink is
    added with the same level.

    Args:
        level (`str`, defaults to `"WARNING"`):
            Loguru level name.
        filepath (`str | None`, optional):
            If provided, log output is additionally written to this file.
        rotation (`str | int | None`, optional):
            File rotation policy (e.g. ``"10 MB"``, ``"1 day"``).
            Only applies when ``filepath`` is set.
        retention (`str | int | None`, optional):
            Retention policy for rotated files (e.g. ``"7 days"``).
            Only applies when ``filepath`` is set.
        compression (`str | None`, optional):
            Compression format for rotated files (e.g. ``"zip"``).
            Only applies when ``filepath`` is set.
        format (`str | None`, optional):
            Custom loguru format string.  Defaults to the built-in
            log format with coloured timestamps.
        colorize (`bool | None`, optional):
            Force-enable or disable ANSI colours on the stderr sink.
            By default loguru auto-detects based on the terminal.
    """
    level = level.upper()
    fmt = format if format is not None else _LOG_FORMAT

    logger.remove()
    logger.add(
        sys.stderr, 
        level=level, 
        format=fmt, 
        colorize=colorize, 
    )

    if filepath is not None:
        file_kwargs: dict = {"level": level, "format": fmt, "encoding": "utf-8"}
        if rotation is not None:
            file_kwargs["rotation"] = rotation
        if retention is not None:
            file_kwargs["retention"] = retention
        if compression is not None:
            file_kwargs["compression"] = compression
        logger.add(filepath, **file_kwargs)


__all__ = ["logger", "setup_logger"]
