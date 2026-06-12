import pandas as pd

from src.data_sources.base import PriceRequest, ProviderError, standardize_price_frame
from src.data_sources.provider_router import ProviderRouter


def test_cn_does_not_fallback_to_yfinance_by_default() -> None:
    router = ProviderRouter()
    assert router.providers_for("CN", "price") == ["akshare", "baostock", "efinance"]


def test_us_uses_yfinance_by_default() -> None:
    router = ProviderRouter()
    assert router.providers_for("US", "price") == ["yfinance", "efinance"]


def test_provider_attempt_records_fallback_metadata() -> None:
    class FailingSource:
        def get_price(self, request: PriceRequest) -> pd.DataFrame:
            raise ProviderError(
                "rate limited",
                "first",
                retryable=True,
                error_type="rate_limited",
                symbol=request.symbol,
            )

    class WorkingSource:
        def get_price(self, request: PriceRequest) -> pd.DataFrame:
            raw = pd.DataFrame(
                {
                    "Date": ["2024-01-02"],
                    "Open": [10],
                    "High": [11],
                    "Low": [9],
                    "Close": [10.5],
                    "Volume": [100],
                }
            )
            return standardize_price_frame(
                raw,
                request=request,
                provider="second",
                provider_symbol="SPY",
                adjust="raw",
            )

    router = ProviderRouter()
    router.priority = {"US": {"price": ["first", "second"]}}
    router.settings = {"first": {"enabled": True}, "second": {"enabled": True}}
    router.sources = {"first": FailingSource(), "second": WorkingSource()}

    _, attempts = router.get_price(PriceRequest("SPY", "US", "2024-01-01"))
    payload = router.summary(attempts)["attempts"]

    assert payload[0]["ok"] is False
    assert payload[0]["error_type"] == "rate_limited"
    assert payload[0]["retryable"] is True
    assert payload[1]["ok"] is True
    assert payload[1]["fallback_reason"] == "previous providers failed: first"
    assert payload[1]["elapsed_ms"] >= 0
