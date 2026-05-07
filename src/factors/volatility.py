from __future__ import annotations

import pandas as pd


def add_volatility(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["symbol", "date"]).copy()
    returns = df.groupby("symbol")["close"].pct_change()
    df["volatility_20d"] = (
        returns.groupby(df["symbol"]).rolling(20).std().reset_index(level=0, drop=True)
    )
    rolling_max = df.groupby("symbol")["close"].rolling(120).max().reset_index(level=0, drop=True)
    df["drawdown_120d"] = df["close"] / rolling_max - 1
    df["turnover_amount_20d"] = (
        df.groupby("symbol")["amount"].rolling(20).mean().reset_index(level=0, drop=True)
    )
    return df
