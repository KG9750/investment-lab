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


class YFinanceSource:
    name = "yfinance"

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError(
                "yfinance is not installed",
                self.name,
                retryable=False,
                error_type="missing_dependency",
                symbol=request.symbol,
            ) from exc
        adjust, auto_adjust = resolve_adjust(self.name, request.adjust)
        provider_symbol = provider_symbol_for(request.symbol, request.market, self.name)
        try:
            if request.timeout_seconds and request.timeout_seconds <= 10:
                raw = _download_chart_api(
                    provider_symbol=provider_symbol,
                    start=request.start,
                    end=request.end,
                    timeout_seconds=request.timeout_seconds,
                )
            else:
                raw = yf.download(
                    provider_symbol,
                    start=request.start,
                    end=request.end,
                    auto_adjust=bool(auto_adjust),
                    progress=False,
                    threads=False,
                    timeout=request.timeout_seconds,
                )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                str(exc),
                self.name,
                retryable=True,
                error_type=classify_provider_exception(exc),
                symbol=request.symbol,
            ) from exc
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return standardize_price_frame(
            raw,
            request=request,
            provider=self.name,
            provider_symbol=provider_symbol,
            adjust=adjust,
        )


def _download_chart_api(
    *,
    provider_symbol: str,
    start: str,
    end: str | None,
    timeout_seconds: int,
) -> pd.DataFrame:
    try:
        import requests

        period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
        end_ts = pd.Timestamp(end, tz="UTC") if end else pd.Timestamp.now("UTC")
        period2 = int((end_ts + pd.Timedelta(days=1)).timestamp())
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}",
            params={
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise ProviderError(
            str(exc),
            "yfinance",
            retryable=True,
            error_type=classify_provider_exception(exc),
            symbol=provider_symbol,
        ) from exc
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return pd.DataFrame()
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(timestamps, unit="s", utc=True).date,
            "Open": quote.get("open", []),
            "High": quote.get("high", []),
            "Low": quote.get("low", []),
            "Close": quote.get("close", []),
            "Volume": quote.get("volume", []),
        }
    )
    return frame.dropna(subset=["Open", "High", "Low", "Close"])
