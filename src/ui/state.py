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


def recent_quality_events(limit: int = 20):
    with connect(read_only=False) as con:
        return con.execute(
            """
            SELECT created_at, event_type, severity, market, symbol, provider, message, retryable
            FROM data_quality_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()


def recent_provider_health(limit: int = 50):
    with connect(read_only=False) as con:
        return con.execute(
            """
            SELECT created_at, market, provider, symbol, severity, message, retryable, details
            FROM data_quality_events
            WHERE event_type = 'provider_health'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()


def recent_cross_provider_checks(limit: int = 50):
    with connect(read_only=False) as con:
        return con.execute(
            """
            SELECT created_at, market, provider, symbol, severity, message, retryable, details
            FROM data_quality_events
            WHERE event_type = 'cross_provider_check'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
