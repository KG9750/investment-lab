from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


def configure_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=getattr(logging, (level or os.getenv("INVESTMENT_LOG_LEVEL", "INFO")).upper()),
        format="%(message)s",
        stream=sys.stderr,
    )


def log_event(logger: logging.Logger, level: int, **payload: Any) -> None:
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
