import pandas as pd

from src.indicators import add_indicators


def test_add_indicators_outputs_expected_columns() -> None:
    prices = pd.DataFrame(
        {
            "symbol": ["SPY"] * 80,
            "date": pd.date_range("2024-01-01", periods=80),
            "open": range(80),
            "high": range(1, 81),
            "low": range(80),
            "close": range(1, 81),
            "volume": [100] * 80,
        }
    )
    out = add_indicators(prices)
    for col in ["ma20", "ma60", "ema12", "macd", "rsi14", "atr14", "boll_upper", "adx14", "obv"]:
        assert col in out.columns
