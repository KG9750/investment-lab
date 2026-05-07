from __future__ import annotations

from src.data_sources.base import PriceRequest, ProviderError


class OpenBBSource:
    name = "openbb"

    def get_price(self, request: PriceRequest):
        raise ProviderError("OpenBB is optional in phase one and is not enabled", self.name, False)
