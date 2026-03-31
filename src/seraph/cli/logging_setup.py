"""Structlog configuration for the Seraph CLI.

Quiet by default (WARNING+ to console, DEBUG+ to ~/.seraph/seraph.log).
Pass ``verbose=True`` to surface DEBUG logs to the console as well.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog


def configure_logging(verbose: bool = False) -> None:
    """Set up structlog for the CLI session.

    Routes all structlog output through stdlib logging so that handler
    levels are respected.  By default only WARNING+ reaches the console;
    DEBUG+ always goes to ~/.seraph/seraph.log.

    Args:
        verbose: If True, stream DEBUG logs to stderr as well.
    """
    log_dir = Path.home() / ".seraph"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "seraph.log"

    # Use stdlib logger factory so handler-level filtering actually works.
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # Stdlib formatter is minimal — structlog already formats the message.
    fmt = logging.Formatter("%(message)s")

    # File handler: always DEBUG, rotates at 5 MB.
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler: WARNING by default, DEBUG if --verbose.
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG if verbose else logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Silence noisy third-party loggers regardless of mode.
    for noisy in ("httpx", "httpcore", "anthropic", "neo4j", "qdrant_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
