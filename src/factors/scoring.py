from __future__ import annotations

import pandas as pd


def add_rank_percentiles(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    out = df.copy()
    for field in fields:
        if field in out.columns:
            out[f"{field}_rank_pct"] = out[field].rank(pct=True, ascending=False)
    return out


def zscore(series: pd.Series) -> pd.Series:
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0
    return (series - series.mean()) / std
