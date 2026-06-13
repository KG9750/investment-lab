from pathlib import Path

import pandas as pd

from src.data_quality.checks import check_price_frame, run_price_quality_checks
from src.storage.parquet_store import ParquetStore


def test_quality_detects_invalid_prices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.data_quality.checks.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    df = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "provider_symbol": "SPY",
                "market": "US",
                "date": "2024-01-02",
                "open": 1,
                "high": 0,
                "low": 1,
                "close": 2,
                "volume": 100,
                "amount": 0,
                "adjust": "auto_adjusted",
                "currency": "USD",
                "provider": "test",
                "row_fetched_at": "2024-01-02T00:00:00Z",
                "snapshot_id": "s1",
            }
        ]
    )
    store.write_prices(df, "US")
    report, _ = run_price_quality_checks(snapshot_id="s1", market="US")
    assert "invalid_ohlc" in set(report["check_type"])


def test_quality_detects_duplicate_persisted_prices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.data_quality.checks.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    df = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "provider_symbol": "SPY",
                "market": "US",
                "date": "2024-01-02",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 100,
                "amount": 0,
                "adjust": "auto_adjusted",
                "currency": "USD",
                "provider": "test",
                "row_fetched_at": "2024-01-02T00:00:00Z",
                "snapshot_id": "s1",
            }
        ]
    )
    store.write_prices(df, "US")
    store.write_prices(df.assign(row_fetched_at="2024-01-03T00:00:00Z"), "US")

    report, _ = run_price_quality_checks(snapshot_id="s1", market="US")

    assert "duplicate_price" in set(report["check_type"])


def test_quality_detects_missing_mixed_synthetic_and_stale(monkeypatch) -> None:
    df = pd.DataFrame(
        [
            _price_row("CN", "000001.SZ", "2024-01-02", "baostock"),
            _price_row("CN", "000001.SZ", "2024-01-04", "baostock"),
            _price_row("CN", "000001.SZ", "2024-01-04", "synthetic"),
        ]
    )
    monkeypatch.setattr(
        "src.data_quality.checks.get_trading_days",
        lambda market, start, end: [
            pd.Timestamp("2024-01-02").date(),
            pd.Timestamp("2024-01-03").date(),
            pd.Timestamp("2024-01-04").date(),
        ],
    )
    monkeypatch.setattr(
        "src.data_quality.checks.previous_trading_day",
        lambda market, date_: pd.Timestamp("2024-01-05").date(),
    )

    report = check_price_frame(df, market="CN")
    checks = set(report["check_type"])

    assert "missing_trading_days" in checks
    assert "mixed_provider_same_day" in checks
    assert "synthetic_price_present" in checks
    assert "stale_symbol" in checks


def _price_row(market: str, symbol: str, date: str, provider: str) -> dict:
    return {
        "symbol": symbol,
        "provider_symbol": symbol,
        "market": market,
        "date": date,
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10,
        "volume": 100,
        "amount": 1000,
        "adjust": "forward_adjusted",
        "currency": "CNY",
        "provider": provider,
        "row_fetched_at": "2024-01-02T00:00:00Z",
        "snapshot_id": "s1",
    }
