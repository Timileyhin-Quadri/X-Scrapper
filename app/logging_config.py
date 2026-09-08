"""Logging configuration for X Research Collector."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging for the application.

    Never logs bearer tokens, passwords, or other secrets.
    """
    logger = logging.getLogger("x_research_collector")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Also log to file with utf-8 encoding to avoid Windows charmap errors
        file_handler = logging.FileHandler("collector.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
