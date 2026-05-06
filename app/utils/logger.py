"""Project-wide logging: normal (quiet success) vs debug (verbose)."""

from __future__ import annotations

import logging
import sys
from typing import Final

_LOG_NAMESPACE: Final[str] = "ai_job_agent"
_configured = False


def configure_logging(*, debug: bool = False) -> None:
    """
    Configure the ai_job_agent logger tree once.

    - Normal: INFO on package root (success paths stay quiet; use WARNING+ for issues).
    - Debug: DEBUG on package root for detailed extraction traces.
    """
    global _configured
    root = logging.getLogger(_LOG_NAMESPACE)
    level = logging.DEBUG if debug else logging.INFO
    root.setLevel(level)

    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s"),
        )
        root.addHandler(handler)
        root.propagate = False
        _configured = True
    else:
        root.setLevel(level)


def get_logger(suffix: str) -> logging.Logger:
    """Returns ``ai_job_agent.<suffix>`` logger (child of configured package root)."""
    name = f"{_LOG_NAMESPACE}.{suffix}" if suffix else _LOG_NAMESPACE
    return logging.getLogger(name)
