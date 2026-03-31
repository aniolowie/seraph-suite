"""Structlog configuration for the Seraph CLI.

Quiet by default (WARNING+ to console, DEBUG+ to ~/.seraph/seraph.log).
Pass ``verbose=True`` to surface DEBUG logs to the console as well.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog


def configure_logging(verbose: bool = False) -> None:
    """Set up structlog for the CLI session.

    Args:
        verbose: If True, emit DEBUG logs to stderr in addition to the log
                 file.  If False (default), only WARNING+ reaches the console.
    """
    log_dir = Path.home() / ".seraph"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "seraph.log"

    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=False),
    ]

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Root stdlib logger — used by third-party libs.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # File handler: always DEBUG, rotates at 5 MB.
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(fh)

    # Console handler: WARNING by default, DEBUG if --verbose.
    if verbose:
        import sys
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(ch)

    # Silence noisy third-party loggers regardless of mode.
    for noisy in ("httpx", "httpcore", "anthropic", "neo4j", "qdrant_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
