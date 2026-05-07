import pandas as pd

from src.backtest.strategies import ma_cross_returns


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
    assert {"date", "strategy_return", "equity"}.issubset(result.columns)
    assert result["equity"].iloc[-1] > 0
