from __future__ import annotations

import pandas as pd

from src.calendars import month_end_trading_days
from src.indicators import add_indicators


def ma_cross_returns(
    prices: pd.DataFrame,
    fast_window: int,
    slow_window: int,
    costs: dict,
) -> pd.DataFrame:
    df = add_indicators(prices).sort_values(["symbol", "date"]).copy()
    fast = df.groupby("symbol")["close"].transform(lambda s: s.rolling(fast_window).mean())
    slow = df.groupby("symbol")["close"].transform(lambda s: s.rolling(slow_window).mean())
    signal = (fast > slow).groupby(df["symbol"]).shift(1).fillna(False)
    returns = df.groupby("symbol")["close"].pct_change().fillna(0)
    turnover = signal.astype(int).groupby(df["symbol"]).diff().abs().fillna(signal.astype(int))
    cost = float(costs.get("commission", 0)) + float(costs.get("slippage", 0))
    df["strategy_return"] = signal.astype(float) * returns - turnover * cost
    df["is_held"] = signal.astype(bool)
    universe_count = int(df["symbol"].nunique())
    grouped = df.groupby("date", as_index=False).agg(
        strategy_return=("strategy_return", "sum"),
        held_count=("is_held", "sum"),
    )
    portfolio = grouped.rename(columns={"held_count": "held_count"})
    portfolio["strategy_return"] = portfolio["strategy_return"] / max(universe_count, 1)
    portfolio["universe_count"] = universe_count
    portfolio["gross_exposure"] = portfolio["held_count"] / max(universe_count, 1)
    portfolio["cash_weight"] = 1 - portfolio["gross_exposure"]
    portfolio["equity"] = (1 + portfolio["strategy_return"]).cumprod()
    return portfolio


def etf_rotation_returns(
    prices: pd.DataFrame,
    lookback: int,
    top_n: int,
    costs: dict,
    market: str,
) -> pd.DataFrame:
    df = prices.sort_values(["symbol", "date"]).copy()
    df["momentum"] = df.groupby("symbol")["close"].pct_change(lookback)
    df["asset_return"] = df.groupby("symbol")["close"].pct_change().fillna(0)
    dates = sorted(pd.to_datetime(df["date"]).dt.date.unique())
    if not dates:
        return pd.DataFrame(columns=["date", "strategy_return", "equity"])
    rebalance_days = set(month_end_trading_days(market, dates[0], dates[-1]))
    holdings: set[str] = set()
    pending_holdings: set[str] | None = None
    rows: list[dict] = []
    cost = float(costs.get("commission", 0)) + float(costs.get("slippage", 0))
    for day in dates:
        day_rows = df[df["date"] == day]
        turnover = 0.0
        if pending_holdings is not None:
            turnover = len(holdings.symmetric_difference(pending_holdings)) / max(top_n, 1)
            holdings = pending_holdings
            pending_holdings = None
        held = day_rows[day_rows["symbol"].isin(holdings)]
        daily_return = 0.0 if held.empty else float(held["asset_return"].mean())
        rows.append({"date": day, "strategy_return": daily_return - turnover * cost})
        if day in rebalance_days or not holdings:
            ranked = day_rows.dropna(subset=["momentum"]).sort_values("momentum", ascending=False)
            if not ranked.empty:
                pending_holdings = set(ranked.head(top_n)["symbol"])
    out = pd.DataFrame(rows)
    out["equity"] = (1 + out["strategy_return"]).cumprod()
    return out
