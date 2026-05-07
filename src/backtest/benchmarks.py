from __future__ import annotations

import pandas as pd


def benchmark_returns(prices: pd.DataFrame, symbol: str) -> pd.Series:
    series = prices[prices["symbol"] == symbol].sort_values("date").set_index("date")["close"]
    return series.pct_change().fillna(0)
