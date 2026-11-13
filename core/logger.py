"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog


def setup_logging(
    log_level: str = "INFO",
    json_logs: bool = False,
) -> structlog.stdlib.BoundLogger:
    """Configure structlog with colored console or JSON rendering."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


def get_logger(*args: Any, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Obtain a structured logger instance with optional bound context."""
    return structlog.get_logger(*args, **initial_values)
