# marketedge/src/logging_config.py
"""Central logging configuration for Market Edge.

Library modules obtain a logger with ``logging.getLogger(__name__)`` and never
add handlers themselves. Application entry points (the CLI, the TUI) call
``configure_logging()`` once at startup. Logs are emitted on stderr so stdout
stays reserved for machine-readable CLI output (dashboard / opportunity JSON).

The level defaults to the ``MARKETEDGE_LOG_LEVEL`` environment variable and
falls back to ``INFO``.
"""

import logging
import os
import sys
from typing import Optional, TextIO

PACKAGE_LOGGER = "src"
ENV_LEVEL = "MARKETEDGE_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"

_configured = False


def configure_logging(
    level: Optional[str] = None, *, stream: Optional[TextIO] = None
) -> logging.Logger:
    """Configure the package logger. Idempotent: handlers are added once.

    Repeated calls only update the effective level, so it is safe to call from
    every entry point without producing duplicate log lines.
    """
    global _configured

    resolved = (level or os.getenv(ENV_LEVEL) or DEFAULT_LEVEL).upper()
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(resolved)

    if not _configured:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        logger.addHandler(handler)
        logger.propagate = False
        _configured = True

    return logger
