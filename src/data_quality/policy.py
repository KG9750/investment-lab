from __future__ import annotations

from typing import Any

import pandas as pd

from src.storage.parquet_store import price_status


def prepare_research_prices(
    prices: pd.DataFrame,
    *,
    market: str,
    requested_symbols: list[str],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    effective = prices.copy()
    allow_synthetic = config.get("allow_synthetic") is not False
    if not allow_synthetic:
        effective = effective[effective["provider"].astype(str) != "synthetic"].copy()

    policy = config.get("quality_policy")
    if policy != "real_research":
        return effective, {"policy": policy or "default", "enabled": False}

    max_stale = int(config.get("max_stale_symbols", 0))
    min_coverage = float(config.get("min_real_coverage_pct", 1.0))
    rows = price_status(effective, market=market, requested_symbols=requested_symbols)
    raw_rows = price_status(prices, market=market, requested_symbols=requested_symbols)
    raw_by_symbol = {row["symbol"]: row for row in raw_rows}
    findings: list[dict[str, Any]] = []
    ready_count = sum(1 for row in rows if row["status"] == "ready")
    stale_count = sum(1 for row in rows if row["status"] == "stale")

    for row in rows:
        raw_status = raw_by_symbol.get(row["symbol"], {})
        status = row["status"]
        if status == "missing" and raw_status.get("status") == "synthetic_only":
            status = "synthetic_only"
        if status in {"missing", "synthetic_only", "mixed_provider"}:
            findings.append(
                {
                    "symbol": row["symbol"],
                    "check_type": status,
                    "severity": "blocking",
                    "message": f"{row['symbol']} failed real_research quality: {status}",
                }
            )
        elif status == "stale" and stale_count > max_stale:
            findings.append(
                {
                    "symbol": row["symbol"],
                    "check_type": "stale",
                    "severity": "blocking",
                    "message": f"{row['symbol']} failed real_research quality: stale",
                }
            )

    coverage = ready_count / len(requested_symbols) if requested_symbols else 0.0
    if coverage < min_coverage:
        findings.append(
            {
                "symbol": None,
                "check_type": "real_coverage_below_minimum",
                "severity": "blocking",
                "message": (
                    f"real_research coverage {coverage:.2%} below required "
                    f"{min_coverage:.2%}"
                ),
            }
        )

    summary = {
        "policy": policy,
        "enabled": True,
        "research_ready_symbol_count": ready_count,
        "stale_symbol_count": stale_count,
        "symbol_count": len(requested_symbols),
        "real_coverage_pct": coverage,
        "findings": findings,
        "symbols": rows,
    }
    if findings:
        checks = ", ".join(sorted({item["check_type"] for item in findings}))
        raise ValueError(f"real_research quality gate failed: {checks}")
    return effective, summary
