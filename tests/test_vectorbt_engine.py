from pathlib import Path

import pandas as pd

from src.backtest.vectorbt_engine import run_backtest
from src.storage.parquet_store import ParquetStore


def test_backtest_meta_includes_traceability(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.storage.parquet_store.DATA_DIR", tmp_path)
    monkeypatch.setattr("src.backtest.vectorbt_engine.DATA_DIR", tmp_path)
    store = ParquetStore(tmp_path)
    rows = []
    for symbol in ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD"]:
        for n, date in enumerate(pd.bdate_range("2024-01-01", periods=90)):
            close = 100 + n
            rows.append(
                {
                    "symbol": symbol,
                    "provider_symbol": symbol,
                    "market": "US",
                    "date": date.date(),
                    "open": close,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "volume": 100,
                    "amount": close * 100,
                    "adjust": "auto_adjusted",
                    "currency": "USD",
                    "provider": "test",
                    "row_fetched_at": "2024-01-01T00:00:00Z",
                    "snapshot_id": "bt_snapshot",
                }
            )
    store.write_prices(pd.DataFrame(rows), "US")
    config = tmp_path / "backtest.yaml"
    config.write_text(
        """
name: test_rotation
market: US
universe: US_ETF_ROTATION
start: "2024-01-01"
end: latest
benchmark:
  symbol: SPY
  return_type: adjusted_price
  dividend_adjusted: unknown
strategy:
  type: etf_rotation
  lookback: 20
  top_n: 2
rebalance: monthly
costs:
  commission: 0
  slippage: 0
output:
  report: false
  quantstats: false
""",
        encoding="utf-8",
    )
    _, meta = run_backtest(config)
    assert meta["snapshot_id"] == "bt_snapshot"
    assert meta["data_range_start"] is not None
    assert meta["data_range_end"] is not None
    assert meta["provider_summary"]["providers"] == ["test"]
