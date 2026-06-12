from __future__ import annotations

import pandas as pd

from src.data_sources.base import (
    PriceRequest,
    ProviderError,
    classify_provider_exception,
    provider_symbol_for,
    resolve_adjust,
    standardize_price_frame,
)


class AKShareSource:
    name = "akshare"

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:
            raise ProviderError(
                "akshare is not installed",
                self.name,
                retryable=False,
                error_type="missing_dependency",
                symbol=request.symbol,
            ) from exc
        adjust, provider_adjust = resolve_adjust(self.name, request.adjust)
        provider_symbol = provider_symbol_for(request.symbol, request.market, self.name)
        start = request.start.replace("-", "")
        end = (request.end or "").replace("-", "")
        try:
            if request.market == "CN":
                raw = ak.stock_zh_a_hist(
                    symbol=provider_symbol,
                    period="daily",
                    start_date=start,
                    end_date=end or None,
                    adjust=provider_adjust,
                )
            elif request.market == "HK":
                raw = ak.stock_hk_hist(
                    symbol=provider_symbol,
                    period="daily",
                    start_date=start,
                    end_date=end or None,
                    adjust=provider_adjust,
                )
            else:
                raise ProviderError(
                    f"AKShare does not handle market {request.market}",
                    self.name,
                    retryable=False,
                    error_type="unsupported_market",
                    symbol=request.symbol,
                )
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(
                str(exc),
                self.name,
                retryable=True,
                error_type=classify_provider_exception(exc),
                symbol=request.symbol,
            ) from exc
        return standardize_price_frame(
            raw,
            request=request,
            provider=self.name,
            provider_symbol=provider_symbol,
            adjust=adjust,
        )
