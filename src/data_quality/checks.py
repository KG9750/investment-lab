from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import DATA_DIR
from src.storage.parquet_store import ParquetStore


def run_price_quality_checks(
    snapshot_id: str | None = None,
    market: str | None = None,
) -> tuple[pd.DataFrame, Path | None]:
    df = ParquetStore().read_prices(market=market)
    if snapshot_id and not df.empty and "snapshot_id" in df.columns:
        df = df[df["snapshot_id"] == snapshot_id]
    report = check_price_frame(df, snapshot_id=snapshot_id, market=market)
    report_path = None
    if not report.empty:
        report_path = (
            DATA_DIR / "metadata" / f"data_quality_{snapshot_id or market or 'all'}.parquet"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report.to_parquet(report_path, index=False)
    return report, report_path


def check_price_frame(
    df: pd.DataFrame,
    snapshot_id: str | None = None,
    market: str | None = None,
) -> pd.DataFrame:
    checks: list[dict] = []
    if df.empty:
        checks.append(
            {
                "snapshot_id": snapshot_id,
                "run_id": None,
                "market": market,
                "symbol": None,
                "check_type": "empty_dataset",
                "severity": "blocking",
                "message": "No price data found for requested quality check",
                "affected_rows": 0,
                "created_at": pd.Timestamp.now("UTC").isoformat(),
            }
        )
    else:
        duplicated = df.duplicated(["market", "symbol", "date", "adjust", "provider"], keep=False)
        if duplicated.any():
            checks.append(_row(df, "duplicate_price", "blocking", int(duplicated.sum())))
        invalid_price = (
            (df["open"] <= 0)
            | (df["high"] <= 0)
            | (df["low"] <= 0)
            | (df["close"] <= 0)
            | (df["high"] < df[["open", "close", "low"]].max(axis=1))
            | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        )
        if invalid_price.any():
            checks.append(_row(df, "invalid_ohlc", "blocking", int(invalid_price.sum())))
        returns = df.sort_values(["symbol", "date"]).groupby("symbol")["close"].pct_change()
        extreme = returns.abs() > 0.25
        if extreme.any():
            checks.append(_row(df, "extreme_daily_return", "warning", int(extreme.sum())))
        zero_volume = df.groupby("symbol")["volume"].transform(
            lambda s: (s.fillna(0) == 0).rolling(20).sum()
        )
        if (zero_volume >= 20).any():
            checks.append(_row(df, "zero_volume_20d", "warning", int((zero_volume >= 20).sum())))
    return pd.DataFrame(checks)


def _row(df: pd.DataFrame, check_type: str, severity: str, affected_rows: int) -> dict:
    return {
        "snapshot_id": df["snapshot_id"].dropna().iloc[-1] if "snapshot_id" in df else None,
        "run_id": None,
        "market": df["market"].dropna().iloc[-1] if "market" in df else None,
        "symbol": None,
        "check_type": check_type,
        "severity": severity,
        "message": f"{check_type} affected {affected_rows} rows",
        "affected_rows": affected_rows,
        "created_at": pd.Timestamp.now("UTC").isoformat(),
    }
