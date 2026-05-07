from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, interval_ms: int) -> None:
        self.interval = interval_ms / 1000
        self.last = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last = time.time()
