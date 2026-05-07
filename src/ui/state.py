from __future__ import annotations

from src.storage.duckdb_client import connect


def recent_runs(limit: int = 20):
    with connect(read_only=False) as con:
        return con.execute(
            "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchdf()


def recent_snapshots(limit: int = 20):
    with connect(read_only=False) as con:
        return con.execute(
            "SELECT * FROM data_snapshots ORDER BY snapshot_created_at DESC LIMIT ?",
            [limit],
        ).fetchdf()
