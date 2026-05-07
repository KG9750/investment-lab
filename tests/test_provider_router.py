from src.data_sources.provider_router import ProviderRouter


def test_cn_does_not_fallback_to_yfinance_by_default() -> None:
    router = ProviderRouter()
    assert router.providers_for("CN", "price") == ["akshare"]


def test_us_uses_yfinance_by_default() -> None:
    router = ProviderRouter()
    assert router.providers_for("US", "price") == ["yfinance"]
