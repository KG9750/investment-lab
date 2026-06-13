from pathlib import Path

import pandas as pd
import pytest

from src.backtest.strategies import etf_rotation_returns, ma_cross_returns
from src.backtest.vectorbt_engine import run_backtest
from src.storage.parquet_store import ParquetStore


def test_ma_cross_shifts_signal() -> None:
    prices = pd.DataFrame(
        {
            "symbol": ["SPY"] * 90,
            "date": pd.date_range("2024-01-01", periods=90),
            "open": range(1, 91),
            "high": range(2, 92),
            "low": range(1, 91),
            "close": range(1, 91),
            "volume": [100] * 90,
        }
    )
    result = ma_cross_returns(prices, 5, 20, {"commission": 0, "slippage": 0})
    assert {
        "date",
        "strategy_return",
        "gross_strategy_return",
        "cost_return",
        "turnover",
        "equity",
        "drawdown",
    }.issubset(result.columns)
    assert result["equity"].iloc[-1] > 0


def test_etf_rotation_does_not_use_same_day_momentum_return() -> None:
    rows = []
    prices = {
        "A": [100, 99, 98, 200],
        "B": [100, 101, 102, 102],
    }
    for symbol, closes in prices.items():
        for date, close in zip(pd.bdate_range("2024-01-01", periods=4), closes, strict=True):
            rows.append({"symbol": symbol, "date": date.date(), "close": close})
    result = etf_rotation_returns(
        pd.DataFrame(rows),
        lookback=1,
        top_n=1,
        costs={"commission": 0, "slippage": 0},
        market="US",
    )
    assert result.loc[result["date"] == pd.Timestamp("2024-01-04").date(), "strategy_return"].iloc[
        0
    ] == 0
    assert {"turnover", "cost_return", "held_symbols", "drawdown"}.issubset(result.columns)


def test_backtest_real_research_blocks_synthetic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.backtest.vectorbt_engine.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    rows = []
    for symbol in ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD"]:
        for date in pd.bdate_range("2024-01-01", periods=90):
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
    config = tmp_path / "backtest.yaml"
    config.write_text(
        """
name: synthetic_backtest
market: US
universe: US_ETF_ROTATION
allow_synthetic: false
quality_policy: real_research
start: "2024-01-01"
end: latest
strategy:
  type: ma_cross
  fast_window: 5
  slow_window: 20
costs:
  commission: 0
  slippage: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="real_research quality gate failed"):
        run_backtest(config)
