import pandas as pd

from src.backtest.strategies import etf_rotation_returns, ma_cross_returns


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
