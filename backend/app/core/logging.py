"""Structured, privacy-preserving logging.

Logs are emitted as JSON in production so they can be shipped to any log sink
without a parser.  Document text and user questions are never logged; only
identifiers, sizes and timings are, which keeps potentially privileged legal
content out of observability systems.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure ``structlog`` and the stdlib root logger for the process."""
    # ``ConsoleRenderer`` formats exceptions itself and warns if handed
    # pre-formatted ones, so ``format_exc_info`` is only added for JSON output.
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.is_production:
        processors += [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.WARNING if settings.is_production else logging.INFO,
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.WARNING if settings.is_production else logging.INFO
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger for ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
