from __future__ import annotations

from typing import Any

import pandas as pd


def enrich_rule_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"close", "ma60"}.issubset(out.columns):
        out["close_above_ma60"] = out["close"] > out["ma60"]
    if {"close", "ma120"}.issubset(out.columns):
        out["close_above_ma120"] = out["close"] > out["ma120"]
    if {"ma20", "ma60"}.issubset(out.columns):
        out["ma20_above_ma60"] = out["ma20"] > out["ma60"]
    return out


def apply_filter(df: pd.DataFrame, rule: dict[str, Any]) -> pd.DataFrame:
    field = rule["field"]
    op = rule.get("op", "eq")
    value = rule.get("value")
    if field not in df.columns:
        return df.iloc[0:0]
    if op == "eq":
        mask = df[field] == value
    elif op == "gt":
        mask = df[field] > value
    elif op == "ge":
        mask = df[field] >= value
    elif op == "lt":
        mask = df[field] < value
    elif op == "le":
        mask = df[field] <= value
    else:
        raise ValueError(f"Unsupported filter op: {op}")
    return df[mask]
