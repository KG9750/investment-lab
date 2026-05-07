from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry(call: Callable[[], T], max_retries: int = 2, base_delay: float = 0.5) -> T:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return call()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc
