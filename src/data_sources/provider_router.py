from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import CONFIG_DIR, load_yaml
from src.data_sources.akshare_source import AKShareSource
from src.data_sources.base import PriceRequest, ProviderError, sleep_ms
from src.data_sources.openbb_source import OpenBBSource
from src.data_sources.yfinance_source import YFinanceSource


@dataclass
class ProviderAttempt:
    provider: str
    ok: bool
    message: str | None = None


class ProviderRouter:
    def __init__(
        self,
        provider_priority_path: str | Path = CONFIG_DIR / "provider_priority.yaml",
        data_sources_path: str | Path = CONFIG_DIR / "data_sources.yaml",
    ) -> None:
        self.priority = load_yaml(provider_priority_path)
        self.settings = load_yaml(data_sources_path)
        self.sources = {
            "akshare": AKShareSource(),
            "yfinance": YFinanceSource(),
            "openbb": OpenBBSource(),
        }

    def providers_for(self, market: str, dataset: str = "price") -> list[str]:
        providers = self.priority.get(market, {}).get(dataset, [])
        return [
            provider
            for provider in providers
            if self.settings.get(provider, {}).get("enabled", False)
        ]

    def get_price(self, request: PriceRequest) -> tuple[pd.DataFrame, list[ProviderAttempt]]:
        attempts: list[ProviderAttempt] = []
        for provider in self.providers_for(request.market, "price"):
            source = self.sources.get(provider)
            if source is None:
                attempts.append(ProviderAttempt(provider, False, "provider is not implemented"))
                continue
            sleep_ms(int(self.settings.get(provider, {}).get("request_interval_ms", 0)))
            try:
                df = source.get_price(request)
                if not df.empty:
                    attempts.append(ProviderAttempt(provider, True))
                    return df, attempts
                attempts.append(ProviderAttempt(provider, False, "empty response"))
            except ProviderError as exc:
                attempts.append(ProviderAttempt(provider, False, str(exc)))
                if not exc.retryable:
                    continue
        return pd.DataFrame(), attempts

    def summary(self, attempts: list[ProviderAttempt]) -> dict[str, Any]:
        return {
            "attempts": [
                {"provider": item.provider, "ok": item.ok, "message": item.message}
                for item in attempts
            ]
        }
