from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from src.storage.metadata import utc_now_str
from src.symbols.mappings import MARKET_CURRENCY
from src.symbols.normalize import denormalize_symbol, normalize_symbol

ADJUST_VALUES = {
    "raw",
    "forward_adjusted",
    "backward_adjusted",
    "auto_adjusted",
    "total_return_adjusted",
    "unknown",
}

AKSHARE_ADJUST_MAP = {
    "": "raw",
    "none": "raw",
    "raw": "raw",
    "qfq": "forward_adjusted",
    "hfq": "backward_adjusted",
}


class ProviderError(RuntimeError):
    def __init__(self, message: str, provider: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


@dataclass(frozen=True)
class PriceRequest:
    symbol: str
    market: str
    start: str
    end: str | None = None
    adjust: str = "provider_default"
    snapshot_id: str | None = None


class PriceSource(Protocol):
    name: str

    def get_price(self, request: PriceRequest) -> pd.DataFrame:
        ...


def resolve_adjust(provider: str, requested: str) -> tuple[str, object]:
    requested = requested or "provider_default"
    if provider == "yfinance":
        if requested == "provider_default":
            return "auto_adjusted", True
        if requested == "auto_adjusted":
            return "auto_adjusted", True
        return "raw", False
    if provider == "akshare":
        if requested == "provider_default":
            return "forward_adjusted", "qfq"
        if requested == "forward_adjusted":
            return "forward_adjusted", "qfq"
        if requested == "backward_adjusted":
            return "backward_adjusted", "hfq"
        return "raw", ""
    if requested not in ADJUST_VALUES:
        return "unknown", requested
    return requested, requested


def standardize_price_frame(
    raw: pd.DataFrame,
    *,
    request: PriceRequest,
    provider: str,
    provider_symbol: str,
    adjust: str,
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    rename = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    }
    df = raw.reset_index().rename(columns=rename)
    if "date" not in df.columns and "index" in df.columns:
        df = df.rename(columns={"index": "date"})
    required = ["date", "open", "high", "low", "close"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ProviderError(f"Missing price columns {missing}", provider=provider, retryable=False)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce")
    unified_symbol = normalize_symbol(request.symbol, request.market, provider)
    fetched_at = utc_now_str()
    df["symbol"] = unified_symbol
    df["provider_symbol"] = provider_symbol
    df["market"] = request.market
    df["adjust"] = adjust
    df["currency"] = MARKET_CURRENCY.get(request.market, "UNKNOWN")
    df["provider"] = provider
    df["row_fetched_at"] = fetched_at
    df["snapshot_id"] = request.snapshot_id
    columns = [
        "symbol",
        "provider_symbol",
        "market",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjust",
        "currency",
        "provider",
        "row_fetched_at",
        "snapshot_id",
    ]
    return df[columns].sort_values(["symbol", "date"]).reset_index(drop=True)


def sleep_ms(milliseconds: int) -> None:
    if milliseconds > 0:
        time.sleep(milliseconds / 1000)


def provider_symbol_for(symbol: str, market: str, provider: str) -> str:
    return denormalize_symbol(normalize_symbol(symbol, market, provider), market, provider)
