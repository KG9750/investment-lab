from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.strategies import etf_rotation_returns, ma_cross_returns
from src.config import DATA_DIR, load_yaml
from src.data_quality.checks import check_price_frame
from src.data_quality.policy import prepare_research_prices
from src.screening.universe import get_universe_config, get_universe_members
from src.storage.metadata import make_run_id
from src.storage.parquet_store import ParquetStore, canonicalize_prices


def run_backtest(config_path: str | Path) -> tuple[pd.DataFrame, dict]:
    config = load_yaml(config_path)
    market = config["market"]
    universe_config = get_universe_config(config["universe"])
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
    prices = canonicalize_prices(prices)
    prices, quality_policy = prepare_research_prices(
        prices,
        market=market,
        requested_symbols=members,
        config=config,
    )
    quality = check_price_frame(prices[prices["symbol"].isin(members)].copy(), market=market)
    blocking = quality[quality["severity"] == "blocking"] if not quality.empty else quality
    if not blocking.empty:
        checks = ", ".join(sorted(blocking["check_type"].unique()))
        raise ValueError(f"Blocking data-quality checks failed before backtest: {checks}")
    strategy_prices = prices[prices["symbol"].isin(members)].copy()
    if strategy_prices.empty:
        raise ValueError(f"No strategy price data found for universe {config['universe']}")
    strategy = config["strategy"]
    if strategy["type"] == "ma_cross":
        result = ma_cross_returns(
            strategy_prices,
            int(strategy.get("fast_window", 20)),
            int(strategy.get("slow_window", 60)),
            config.get("costs", {}),
        )
    elif strategy["type"] == "etf_rotation":
        result = etf_rotation_returns(
            strategy_prices,
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
    if "turnover" in result:
        stats["turnover"] = float(result["turnover"].fillna(0).sum())
    if "gross_exposure" in result:
        stats["average_gross_exposure"] = float(result["gross_exposure"].fillna(0).mean())
    if "cost_return" in result:
        stats["total_cost_return"] = float(result["cost_return"].fillna(0).sum())
    meta = {
        "run_id": run_id,
        "path": str(out_path),
        "config": config,
        "strategy": strategy,
        "costs": config.get("costs", {}),
        "benchmark": config.get("benchmark", {}),
        "universe": {
            "name": config["universe"],
            "membership_mode": universe_config.get("membership_mode"),
            "provider": universe_config.get("provider"),
            "member_count": len(members),
        },
        "adjust": sorted(strategy_prices["adjust"].dropna().astype(str).unique()),
        "snapshot_id": ",".join(
            sorted(strategy_prices["snapshot_id"].dropna().astype(str).unique())
        ),
        "data_range_start": strategy_prices["date"].min(),
        "data_range_end": strategy_prices["date"].max(),
        "provider_summary": {
            "providers": sorted(strategy_prices["provider"].dropna().astype(str).unique()),
            "symbols": sorted(strategy_prices["symbol"].dropna().astype(str).unique()),
            "benchmark": benchmark,
        },
        "quality_policy": quality_policy,
        **stats,
    }
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
        "average_gross_exposure": None,
        "total_cost_return": None,
    }
