from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import duckdb
import pandas as pd

from src.calendars import next_trading_day
from src.config import DATA_DIR, ensure_data_dirs

PRICE_KEYS = ["market", "symbol", "date", "adjust", "provider"]
CANONICAL_PRICE_KEYS = ["market", "symbol", "date"]


def next_resume_start(market: str, latest_date) -> str:
    latest = pd.Timestamp(latest_date).date()
    try:
        return next_trading_day(market, latest).isoformat()
    except Exception:
        return (pd.Timestamp(latest) + pd.Timedelta(days=1)).date().isoformat()


class ParquetStore:
    def __init__(self, root: Path | None = None) -> None:
        ensure_data_dirs()
        self.root = root or DATA_DIR

    @property
    def prices_root(self) -> Path:
        return self.root / "processed" / "prices"

    def write_prices(self, prices: pd.DataFrame, market: str) -> list[Path]:
        if prices.empty:
            return []
        df = prices.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["date_month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        written: list[Path] = []
        for date_month, group in df.groupby("date_month", dropna=False):
            partition = self.prices_root / f"market={market}" / f"date_month={date_month}"
            partition.mkdir(parents=True, exist_ok=True)
            path = partition / f"part-{uuid.uuid4().hex[:12]}.parquet"
            group.drop(columns=["date_month"]).to_parquet(path, index=False)
            written.append(path)
        return written

    def _glob(self, dataset_root: Path, market: str | None = None) -> str:
        if market:
            return str(dataset_root / f"market={market}" / "*" / "*.parquet")
        return str(dataset_root / "*" / "*" / "*.parquet")

    def read_prices(
        self,
        market: str | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        deduplicate: bool = True,
    ) -> pd.DataFrame:
        glob_path = self._glob(self.prices_root, market)
        if not list(self.prices_root.glob(f"market={market or '*'}/date_month=*/*.parquet")):
            return pd.DataFrame()
        con = duckdb.connect()
        where = ["1=1"]
        params: list[object] = []
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            where.append(f"symbol IN ({placeholders})")
            params.extend(symbols)
        if start:
            where.append("date >= ?")
            params.append(start)
        if end and end != "latest":
            where.append("date <= ?")
            params.append(end)
        if deduplicate:
            query = f"""
            SELECT * EXCLUDE(rn)
            FROM (
                SELECT *,
                       row_number() OVER (
                         PARTITION BY market, symbol, date, adjust, provider
                         ORDER BY row_fetched_at DESC
                       ) AS rn
                FROM read_parquet('{glob_path}', union_by_name=true)
                WHERE {' AND '.join(where)}
            )
            WHERE rn = 1
            ORDER BY symbol, date
            """
        else:
            query = f"""
                SELECT *
                FROM read_parquet('{glob_path}', union_by_name=true)
                WHERE {' AND '.join(where)}
                ORDER BY symbol, date, row_fetched_at
            """
        return con.execute(query, params).fetch_df()

    def compact_prices(self, market: str | None = None) -> int:
        df = self.read_prices(market=market)
        if df.empty:
            return 0
        target_root = self.prices_root / f"market={market}" if market else self.prices_root
        tmp_root = target_root.with_name(target_root.name + ".tmp")
        if tmp_root.exists():
            shutil.rmtree(tmp_root)
        old_root = target_root.with_name(target_root.name + ".old")
        df["date_month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        for (row_market, date_month), group in df.groupby(["market", "date_month"], dropna=False):
            partition = tmp_root
            if not market:
                partition = tmp_root / f"market={row_market}"
            partition = partition / f"date_month={date_month}"
            partition.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["date_month"]).to_parquet(
                partition / f"part-compact-{uuid.uuid4().hex[:8]}.parquet",
                index=False,
            )
        tmp_glob = (
            str(tmp_root / "date_month=*" / "*.parquet")
            if market
            else str(tmp_root / "market=*" / "date_month=*" / "*.parquet")
        )
        compacted = duckdb.connect().execute(
            f"SELECT * FROM read_parquet('{tmp_glob}', union_by_name=true)"
        ).fetch_df()
        duplicated = compacted.duplicated(PRICE_KEYS, keep=False)
        if len(compacted) != len(df) or duplicated.any():
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise ValueError("Compacted prices failed validation")
        try:
            if old_root.exists():
                shutil.rmtree(old_root)
            if target_root.exists():
                target_root.rename(old_root)
            tmp_root.rename(target_root)
        except Exception:
            if not target_root.exists() and old_root.exists():
                old_root.rename(target_root)
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise
        shutil.rmtree(old_root, ignore_errors=True)
        return len(df)


def canonicalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return prices
    df = prices.copy()
    df["row_fetched_at"] = pd.to_datetime(df["row_fetched_at"], errors="coerce", utc=True)
    df["_provider_rank"] = (df["provider"].astype(str) != "synthetic").astype(int)
    df = df.sort_values(CANONICAL_PRICE_KEYS + ["_provider_rank", "row_fetched_at"])
    df = df.drop_duplicates(CANONICAL_PRICE_KEYS, keep="last")
    return (
        df.drop(columns=["_provider_rank"])
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )


def price_status(
    prices: pd.DataFrame,
    *,
    market: str,
    requested_symbols: list[str],
) -> list[dict]:
    if prices.empty:
        return [
            {
                "market": market,
                "symbol": symbol,
                "row_count": 0,
                "latest_date": None,
                "resume_start": None,
                "providers": [],
                "snapshot_ids": [],
            }
            for symbol in requested_symbols
        ]
    df = canonicalize_prices(prices)
    rows: list[dict] = []
    for symbol in requested_symbols:
        group = df[df["symbol"] == symbol]
        if group.empty:
            rows.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "row_count": 0,
                    "latest_date": None,
                    "resume_start": None,
                    "providers": [],
                    "snapshot_ids": [],
                }
            )
            continue
        latest = pd.to_datetime(group["date"]).max().date()
        rows.append(
            {
                "market": market,
                "symbol": symbol,
                "row_count": int(len(group)),
                "latest_date": latest.isoformat(),
                "resume_start": next_resume_start(market, latest),
                "providers": sorted(group["provider"].dropna().astype(str).unique().tolist()),
                "snapshot_ids": sorted(group["snapshot_id"].dropna().astype(str).unique().tolist()),
            }
        )
    return rows
