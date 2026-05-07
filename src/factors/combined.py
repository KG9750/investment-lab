from __future__ import annotations

import pandas as pd

from src.factors.momentum import add_momentum
from src.factors.scoring import add_rank_percentiles
from src.factors.volatility import add_volatility
from src.storage.metadata import make_snapshot_id, utc_now_str


def add_phase_one_factors(prices: pd.DataFrame, market: str) -> pd.DataFrame:
    if prices.empty:
        return prices.copy()
    df = add_momentum(prices)
    df = add_volatility(df)
    df = add_rank_percentiles(df, ["momentum_60d", "volatility_20d"])
    df["factor_snapshot_id"] = make_snapshot_id(market, "factors")
    df["source_snapshot_id"] = df.get("snapshot_id")
    df["created_at"] = utc_now_str()
    return df
