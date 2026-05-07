from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DATA_DIR, ensure_data_dirs

PRICE_KEYS = ["market", "symbol", "date", "adjust", "provider"]


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
        local_store = ParquetStore(self.root)
        original_root = local_store.prices_root
        try:
            local_store.prices_root_override = tmp_root
        except Exception:
            pass
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
        if old_root.exists():
            shutil.rmtree(old_root)
        if target_root.exists():
            target_root.rename(old_root)
        tmp_root.rename(target_root)
        shutil.rmtree(old_root, ignore_errors=True)
        _ = original_root
        return len(df)
