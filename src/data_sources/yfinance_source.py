from __future__ import annotations

import pandas as pd

from src.data_sources.base import (
    PriceRequest,
    ProviderError,
    provider_symbol_for,
    resolve_adjust,
    standardize_price_frame,
)


class YFinanceSource:
    name = "yfinance"

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError("yfinance is not installed", self.name, retryable=False) from exc
        adjust, auto_adjust = resolve_adjust(self.name, request.adjust)
        provider_symbol = provider_symbol_for(request.symbol, request.market, self.name)
        try:
            raw = yf.download(
                provider_symbol,
                start=request.start,
                end=request.end,
                auto_adjust=bool(auto_adjust),
                progress=False,
                threads=False,
            )
        except Exception as exc:
            raise ProviderError(str(exc), self.name, retryable=True) from exc
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return standardize_price_frame(
            raw,
            request=request,
            provider=self.name,
            provider_symbol=provider_symbol,
            adjust=adjust,
        )
