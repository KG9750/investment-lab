from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(window).mean()
    plus_di = 100 * plus_dm.rolling(window).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(window).mean() / atr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(window).mean()


def _add_group(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("date").copy()
    close = group["close"]
    high = group["high"]
    low = group["low"]
    volume = group["volume"].fillna(0)
    for window in [5, 20, 60, 120, 250]:
        group[f"ma{window}"] = close.rolling(window).mean()
    group["ema12"] = close.ewm(span=12, adjust=False).mean()
    group["ema26"] = close.ewm(span=26, adjust=False).mean()
    group["macd"] = group["ema12"] - group["ema26"]
    group["macd_signal"] = group["macd"].ewm(span=9, adjust=False).mean()
    group["macd_hist"] = group["macd"] - group["macd_signal"]
    group["rsi14"] = _rsi(close, 14)
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    )
    group["atr14"] = tr.max(axis=1).rolling(14).mean()
    group["boll_middle"] = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    group["boll_upper"] = group["boll_middle"] + 2 * boll_std
    group["boll_lower"] = group["boll_middle"] - 2 * boll_std
    group["adx14"] = _adx(high, low, close, 14)
    direction = np.sign(close.diff()).fillna(0)
    group["obv"] = (direction * volume).cumsum()
    return group


def add_indicators(prices: pd.DataFrame, backend: str = "native") -> pd.DataFrame:
    if backend != "native":
        raise ValueError("Only native indicator backend is available in phase one")
    if prices.empty:
        return prices.copy()
    return pd.concat(
        [_add_group(group) for _, group in prices.groupby("symbol", sort=False)],
        ignore_index=True,
    )
