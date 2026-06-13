from pathlib import Path

import pandas as pd
import pytest

from src.storage.parquet_store import ParquetStore, canonicalize_prices


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


def test_compact_restores_old_prices_when_swap_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    original_rename = Path.rename

    def fail_tmp_swap(self: Path, target: Path) -> Path:
        if self.name.endswith(".tmp"):
            raise OSError("simulated swap failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_tmp_swap)

    with pytest.raises(OSError, match="simulated swap failure"):
        store.compact_prices("US")

    out = store.read_prices(market="US", symbols=["SPY"])
    assert len(out) == 1
    assert out.iloc[0]["symbol"] == "SPY"


def test_canonical_prices_prefer_real_provider_over_synthetic() -> None:
    base = {
        "symbol": "000001.SZ",
        "provider_symbol": "000001",
        "market": "CN",
        "date": "2024-01-02",
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 2,
        "volume": 100,
        "amount": 0,
        "adjust": "forward_adjusted",
        "currency": "CNY",
        "row_fetched_at": "2024-01-02T00:00:00Z",
        "snapshot_id": "synthetic_snapshot",
    }
    prices = pd.DataFrame(
        [
            {**base, "provider": "synthetic", "close": 200},
            {
                **base,
                "provider": "baostock",
                "close": 10,
                "row_fetched_at": "2024-01-03T00:00:00Z",
                "snapshot_id": "real_snapshot",
            },
        ]
    )

    out = canonicalize_prices(prices)

    assert len(out) == 1
    assert out.iloc[0]["provider"] == "baostock"
    assert out.iloc[0]["close"] == 10
