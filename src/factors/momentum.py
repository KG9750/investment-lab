from __future__ import annotations

import pandas as pd


def add_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["symbol", "date"]).copy()
    grouped = df.groupby("symbol")["close"]
    for window in [20, 60, 120]:
        df[f"momentum_{window}d"] = grouped.pct_change(window)
    return df
