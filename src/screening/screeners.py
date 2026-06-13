from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import DATA_DIR, load_yaml
from src.data_quality.checks import check_price_frame
from src.data_quality.policy import prepare_research_prices
from src.factors.combined import add_phase_one_factors
from src.indicators import add_indicators
from src.screening.rules import apply_filter, enrich_rule_fields
from src.screening.universe import get_universe_members
from src.storage.metadata import make_run_id
from src.storage.parquet_store import ParquetStore, canonicalize_prices


def run_screen(config_path: str | Path) -> tuple[pd.DataFrame, dict]:
    config = load_yaml(config_path)
    market = config["market"]
    members = get_universe_members(config["universe"])
    prices = ParquetStore().read_prices(market=market, symbols=members or None)
    if prices.empty:
        raise ValueError(f"No local price data found for screen {config['name']} market={market}")
    prices = canonicalize_prices(prices)
    prices, quality_policy = prepare_research_prices(
        prices,
        market=market,
        requested_symbols=members,
        config=config,
    )
    quality = check_price_frame(prices, market=market)
    blocking = quality[quality["severity"] == "blocking"] if not quality.empty else quality
    if not blocking.empty:
        checks = ", ".join(sorted(blocking["check_type"].unique()))
        raise ValueError(f"Blocking data-quality checks failed before screen: {checks}")
    df = add_phase_one_factors(add_indicators(prices), market)
    latest_dates = df.groupby("symbol")["date"].transform("max")
    latest = enrich_rule_fields(df[df["date"] == latest_dates].copy())
    for rule in config.get("filters", []):
        latest = apply_filter(latest, rule)
    for sort_rule in reversed(config.get("sort", [])):
        latest = latest.sort_values(
            sort_rule["field"],
            ascending=sort_rule.get("direction", "desc") != "desc",
        )
    latest = latest.head(int(config.get("limit", 50))).copy()
    if "score" not in latest.columns:
        latest["score"] = latest.get("momentum_60d_rank_pct", pd.Series(index=latest.index)) * -1
    run_id = make_run_id("screen", market, config["name"], config)
    out_path = DATA_DIR / "screens" / f"{config['name']}_{run_id}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    latest.to_parquet(out_path, index=False)
    meta = {
        "run_id": run_id,
        "path": str(out_path),
        "row_count": len(latest),
        "config": config,
        "quality_policy": quality_policy,
    }
    return latest, meta
