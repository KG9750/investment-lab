from pathlib import Path

import pandas as pd

from src.data_quality.checks import run_price_quality_checks
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
