from pathlib import Path

import pandas as pd

from src.storage.parquet_store import ParquetStore


def test_write_read_prices_dedupes(tmp_path: Path) -> None:
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
    out = store.read_prices(market="US", symbols=["SPY"])
    assert len(out) == 1
    assert out.iloc[0]["row_fetched_at"] == "2024-01-03T00:00:00Z"
