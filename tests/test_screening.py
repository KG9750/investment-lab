from pathlib import Path

import pandas as pd
import pytest

from src.screening.screeners import run_screen
from src.storage.parquet_store import ParquetStore


def test_screen_blocks_invalid_price_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.screening.screeners.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    rows = []
    for date in pd.bdate_range("2024-01-01", periods=130):
        rows.append(
            {
                "symbol": "SPY",
                "provider_symbol": "SPY",
                "market": "US",
                "date": date.date(),
                "open": 1,
                "high": 0,
                "low": 1,
                "close": 2,
                "volume": 100,
                "amount": 200,
                "adjust": "auto_adjusted",
                "currency": "USD",
                "provider": "test",
                "row_fetched_at": "2024-01-01T00:00:00Z",
                "snapshot_id": "screen_bad",
            }
        )
    store.write_prices(pd.DataFrame(rows), "US")
    config = tmp_path / "screen.yaml"
    config.write_text(
        """
name: bad_screen
market: US
universe: US_ETF_ROTATION
filters: []
sort:
  - field: momentum_60d
    direction: desc
limit: 10
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Blocking data-quality"):
        run_screen(config)


def test_screen_real_research_blocks_synthetic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.screening.screeners.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    rows = []
    for symbol in ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD"]:
        for date in pd.bdate_range("2024-01-01", periods=80):
            rows.append(
                {
                    "symbol": symbol,
                    "provider_symbol": symbol,
                    "market": "US",
                    "date": date.date(),
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 100,
                    "amount": 200,
                    "adjust": "auto_adjusted",
                    "currency": "USD",
                    "provider": "synthetic",
                    "row_fetched_at": "2024-01-01T00:00:00Z",
                    "snapshot_id": "synthetic_only",
                }
            )
    store.write_prices(pd.DataFrame(rows), "US")
    config = tmp_path / "screen.yaml"
    config.write_text(
        """
name: synthetic_screen
market: US
universe: US_ETF_ROTATION
allow_synthetic: false
quality_policy: real_research
filters: []
sort:
  - field: momentum_60d
    direction: desc
limit: 10
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="real_research quality gate failed"):
        run_screen(config)
