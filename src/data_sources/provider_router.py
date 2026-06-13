from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import current_thread, main_thread
from typing import Any

import pandas as pd

from src.config import CONFIG_DIR, load_yaml
from src.data_sources.akshare_source import AKShareSource
from src.data_sources.baostock_source import BaoStockSource
from src.data_sources.base import PriceRequest, ProviderError, sleep_ms
from src.data_sources.efinance_source import EFinanceSource
from src.data_sources.openbb_source import OpenBBSource
from src.data_sources.yfinance_source import YFinanceSource


@dataclass
class ProviderAttempt:
    provider: str
    ok: bool
    message: str | None = None
    error_type: str | None = None
    symbol: str | None = None
    elapsed_ms: int = 0
    retryable: bool = False
    fallback_reason: str | None = None
    proxy_mode: str = "env"
    attempt_number: int = 1


class ProviderRouter:
    def __init__(
        self,
        provider_priority_path: str | Path = CONFIG_DIR / "provider_priority.yaml",
        data_sources_path: str | Path = CONFIG_DIR / "data_sources.yaml",
        proxy_mode: str | None = None,
    ) -> None:
        self.priority = load_yaml(provider_priority_path)
        self.settings = load_yaml(data_sources_path)
        self.proxy_mode = proxy_mode
        self.sources = {
            "akshare": AKShareSource(),
            "baostock": BaoStockSource(),
            "efinance": EFinanceSource(),
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
        failed_providers: list[str] = []
        for provider in self.providers_for(request.market, "price"):
            fallback_reason = (
                f"previous providers failed: {','.join(failed_providers)}"
                if failed_providers
                else None
            )
            df, provider_attempts = self.get_price_from_provider_attempts(
                provider,
                request,
                fallback_reason=fallback_reason,
            )
            attempts.extend(provider_attempts)
            if provider_attempts and provider_attempts[-1].ok:
                return df, attempts
            failed_providers.append(provider)
        return pd.DataFrame(), attempts

    def get_price_from_provider(
        self,
        provider: str,
        request: PriceRequest,
        *,
        fallback_reason: str | None = None,
    ) -> tuple[pd.DataFrame, ProviderAttempt]:
        df, attempts = self.get_price_from_provider_attempts(
            provider,
            request,
            fallback_reason=fallback_reason,
        )
        return df, attempts[-1]

    def get_price_from_provider_attempts(
        self,
        provider: str,
        request: PriceRequest,
        *,
        fallback_reason: str | None = None,
    ) -> tuple[pd.DataFrame, list[ProviderAttempt]]:
        source = self.sources.get(provider)
        if source is None:
            return pd.DataFrame(), [
                ProviderAttempt(
                    provider=provider,
                    ok=False,
                    message="provider is not implemented",
                    error_type="not_implemented",
                    symbol=request.symbol,
                    retryable=False,
                    fallback_reason=fallback_reason,
                )
            ]
        provider_settings = self.settings.get(provider, {})
        max_retries = max(0, int(provider_settings.get("max_retries", 0) or 0))
        attempts: list[ProviderAttempt] = []
        for attempt_number in range(1, max_retries + 2):
            df, attempt = self._attempt_provider_once(
                provider=provider,
                source=source,
                request=request,
                provider_settings=provider_settings,
                fallback_reason=fallback_reason,
                attempt_number=attempt_number,
            )
            attempts.append(attempt)
            if attempt.ok:
                return df, attempts
            if not attempt.retryable:
                return pd.DataFrame(), attempts
            if attempt_number <= max_retries:
                sleep_ms(self._retry_delay_ms(provider_settings, attempt_number))
        return pd.DataFrame(), attempts

    def _attempt_provider_once(
        self,
        *,
        provider: str,
        source,
        request: PriceRequest,
        provider_settings: dict[str, Any],
        fallback_reason: str | None,
        attempt_number: int,
    ) -> tuple[pd.DataFrame, ProviderAttempt]:
        sleep_ms(int(provider_settings.get("request_interval_ms", 0)))
        proxy_mode = self._proxy_mode_for(provider)
        timeout_seconds = (
            request.timeout_seconds or int(provider_settings.get("timeout_seconds", 0)) or None
        )
        request = replace(request, timeout_seconds=timeout_seconds)
        started = time.perf_counter()
        try:
            with _proxy_environment(proxy_mode):
                df = _call_with_hard_timeout(
                    lambda: source.get_price(request),
                    timeout_seconds=timeout_seconds,
                    provider=provider,
                    symbol=request.symbol,
                )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not df.empty:
                return df, ProviderAttempt(
                    provider=provider,
                    ok=True,
                    message="ok",
                    symbol=request.symbol,
                    elapsed_ms=elapsed_ms,
                    fallback_reason=fallback_reason,
                    proxy_mode=proxy_mode,
                    attempt_number=attempt_number,
                )
            return pd.DataFrame(), ProviderAttempt(
                provider=provider,
                ok=False,
                message="empty response",
                error_type="empty_response",
                symbol=request.symbol,
                elapsed_ms=elapsed_ms,
                retryable=True,
                fallback_reason=fallback_reason,
                proxy_mode=proxy_mode,
                attempt_number=attempt_number,
            )
        except ProviderError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return pd.DataFrame(), ProviderAttempt(
                provider=provider,
                ok=False,
                message=str(exc),
                error_type=exc.error_type,
                symbol=exc.symbol or request.symbol,
                elapsed_ms=elapsed_ms,
                retryable=exc.retryable,
                fallback_reason=fallback_reason,
                proxy_mode=proxy_mode,
                attempt_number=attempt_number,
            )

    def summary(self, attempts: list[ProviderAttempt]) -> dict[str, Any]:
        return {
            "attempts": [
                {
                    "provider": item.provider,
                    "ok": item.ok,
                    "message": item.message,
                    "error_type": item.error_type,
                    "symbol": item.symbol,
                    "elapsed_ms": item.elapsed_ms,
                    "retryable": item.retryable,
                    "fallback_reason": item.fallback_reason,
                    "proxy_mode": item.proxy_mode,
                    "attempt_number": item.attempt_number,
                }
                for item in attempts
            ]
        }

    def _proxy_mode_for(self, provider: str) -> str:
        mode = self.proxy_mode or str(self.settings.get(provider, {}).get("proxy_mode", "env"))
        if mode not in {"env", "direct"}:
            return "env"
        return mode

    def _retry_delay_ms(self, provider_settings: dict[str, Any], attempt_number: int) -> int:
        base = int(provider_settings.get("request_interval_ms", 0) or 0)
        if base <= 0:
            return 0
        if provider_settings.get("retry_backoff") == "exponential":
            return base * (2 ** (attempt_number - 1))
        return base


PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
]


@contextmanager
def _proxy_environment(proxy_mode: str):
    if proxy_mode != "direct":
        yield
        return
    original = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _call_with_hard_timeout(
    callback,
    *,
    timeout_seconds: int | None,
    provider: str,
    symbol: str,
) -> pd.DataFrame:
    if not timeout_seconds or current_thread() is not main_thread():
        return callback()
    import signal

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(signum, frame):
        raise ProviderError(
            f"{provider} timed out after {timeout_seconds}s",
            provider,
            retryable=True,
            error_type="timeout",
            symbol=symbol,
        )

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
