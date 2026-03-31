"""Structlog configuration for the Seraph CLI.

Quiet by default (WARNING+ to console, DEBUG+ to ~/.seraph/seraph.log).
Pass ``verbose=True`` to surface DEBUG logs to the console as well.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def configure_logging(verbose: bool = False) -> None:
    """Set up structlog for the CLI session.

    Args:
        verbose: If True, emit DEBUG logs to stderr in addition to the log
                 file.  If False (default), only WARNING+ reaches the console.
    """
    console_level = logging.DEBUG if verbose else logging.WARNING

    log_dir = Path.home() / ".seraph"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "seraph.log"

    # Root stdlib logger — structlog pipes through this.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # File handler: always DEBUG.
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(fh)

    # Console handler: WARNING by default, DEBUG if --verbose.
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(ch)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=None),
    )

    # Silence noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "anthropic", "neo4j", "qdrant_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
