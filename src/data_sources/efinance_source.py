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


class EFinanceSource:
    name = "efinance"

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        try:
            import efinance as ef
        except ImportError as exc:
            raise ProviderError(
                "efinance is not installed",
                self.name,
                retryable=False,
                error_type="missing_dependency",
                symbol=request.symbol,
            ) from exc

        adjust, provider_adjust = resolve_adjust(self.name, request.adjust)
        provider_symbol = provider_symbol_for(request.symbol, request.market, self.name)
        beg = request.start.replace("-", "")
        end = (request.end or "20500101").replace("-", "")
        market_type = self._market_type(ef, request.market)
        try:
            raw = ef.stock.get_quote_history(
                stock_codes=provider_symbol,
                beg=beg,
                end=end,
                klt=101,
                fqt=int(provider_adjust),
                market_type=market_type,
            )
        except Exception as exc:
            raise ProviderError(
                str(exc),
                self.name,
                retryable=True,
                error_type=classify_provider_exception(exc),
                symbol=request.symbol,
            ) from exc
        if isinstance(raw, dict):
            raw = raw.get(provider_symbol, next(iter(raw.values()), pd.DataFrame()))
        if raw is None or raw.empty:
            raise ProviderError(
                "efinance returned empty response",
                self.name,
                retryable=True,
                error_type="empty_response",
                symbol=request.symbol,
            )
        return standardize_price_frame(
            raw,
            request=request,
            provider=self.name,
            provider_symbol=provider_symbol,
            adjust=adjust,
        )

    def _market_type(self, ef, market: str):
        mapping = {
            "CN": ef.common.config.MarketType.A_stock,
            "HK": ef.common.config.MarketType.Hongkong,
            "US": ef.common.config.MarketType.US_stock,
        }
        if market not in mapping:
            raise ProviderError(
                f"eFinance does not handle market {market}",
                self.name,
                retryable=False,
                error_type="unsupported_market",
            )
        return mapping[market]
