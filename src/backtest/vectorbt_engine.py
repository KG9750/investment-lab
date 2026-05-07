from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.strategies import etf_rotation_returns, ma_cross_returns
from src.config import DATA_DIR, load_yaml
from src.screening.universe import get_universe_members
from src.storage.metadata import make_run_id
from src.storage.parquet_store import ParquetStore


def run_backtest(config_path: str | Path) -> tuple[pd.DataFrame, dict]:
    config = load_yaml(config_path)
    market = config["market"]
    members = get_universe_members(config["universe"])
    benchmark = config.get("benchmark", {}).get("symbol")
    symbols = sorted(set(members + ([benchmark] if benchmark else [])))
    prices = ParquetStore().read_prices(
        market=market,
        symbols=symbols or None,
        start=config.get("start"),
        end=config.get("end"),
    )
    if prices.empty:
        raise ValueError(f"No local price data found for backtest {config['name']} market={market}")
    strategy = config["strategy"]
    if strategy["type"] == "ma_cross":
        result = ma_cross_returns(
            prices[prices["symbol"].isin(members)],
            int(strategy.get("fast_window", 20)),
            int(strategy.get("slow_window", 60)),
            config.get("costs", {}),
        )
    elif strategy["type"] == "etf_rotation":
        result = etf_rotation_returns(
            prices[prices["symbol"].isin(members)],
            int(strategy.get("lookback", 60)),
            int(strategy.get("top_n", 2)),
            config.get("costs", {}),
            market,
        )
    else:
        raise ValueError(f"Unsupported strategy type: {strategy['type']}")
    run_id = make_run_id("backtest", market, config["name"], config)
    out_path = DATA_DIR / "backtests" / f"{config['name']}_{run_id}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    stats = summarize_returns(result["strategy_return"])
    meta = {"run_id": run_id, "path": str(out_path), "config": config, **stats}
    return result, meta


def summarize_returns(returns: pd.Series) -> dict:
    clean = returns.fillna(0)
    total_return = float((1 + clean).prod() - 1)
    annual_return = float((1 + total_return) ** (252 / max(len(clean), 1)) - 1)
    annual_volatility = float(clean.std() * (252**0.5))
    sharpe = annual_return / annual_volatility if annual_volatility else 0.0
    equity = (1 + clean).cumprod()
    drawdown = equity / equity.cummax() - 1
    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe": float(sharpe),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "turnover": None,
    }
