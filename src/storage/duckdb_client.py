from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import duckdb

from src.config import DATA_DIR, ensure_data_dirs

DEFAULT_DB_PATH = DATA_DIR / "investment.duckdb"
MIGRATIONS: list[tuple[int, str]] = [
    (1, "ensure_observability_columns"),
]


def get_db_path() -> Path:
    return Path(os.getenv("INVESTMENT_DB_PATH", str(DEFAULT_DB_PATH)))


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    ensure_data_dirs()
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect_with_retry(db_path, read_only=read_only)
    init_db(con)
    return con


def _connect_with_retry(
    db_path: Path,
    read_only: bool = False,
    attempts: int = 20,
) -> duckdb.DuckDBPyConnection:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return duckdb.connect(str(db_path), read_only=read_only)
        except duckdb.IOException as exc:
            if "Conflicting lock" not in str(exc):
                raise
            last_exc = exc
            time.sleep(0.25 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def init_db(con: duckdb.DuckDBPyConnection | None = None) -> None:
    own_connection = con is None
    if con is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = _connect_with_retry(db_path)
    statements = [
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            task TEXT NOT NULL,
            config_path TEXT,
            config_hash TEXT,
            snapshot_id TEXT,
            data_range_start DATE,
            data_range_end DATE,
            provider_summary TEXT,
            created_at TIMESTAMP,
            finished_at TIMESTAMP,
            status TEXT,
            warning_count INTEGER DEFAULT 0,
            blocking_error_count INTEGER DEFAULT 0,
            report_path TEXT,
            errors TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS data_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            dataset TEXT NOT NULL,
            provider TEXT NOT NULL,
            snapshot_created_at TIMESTAMP NOT NULL,
            min_date DATE,
            max_date DATE,
            row_count BIGINT,
            config_hash TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS index_membership (
            index_code TEXT NOT NULL,
            symbol TEXT NOT NULL,
            in_date DATE NOT NULL,
            out_date DATE,
            provider TEXT NOT NULL,
            row_fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (index_code, symbol, in_date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trading_calendar (
            market TEXT NOT NULL,
            date DATE NOT NULL,
            is_open BOOLEAN NOT NULL,
            session_type TEXT,
            timezone TEXT,
            source TEXT NOT NULL,
            row_fetched_at TIMESTAMP NOT NULL,
            snapshot_id TEXT,
            PRIMARY KEY (market, date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS symbol_master (
            unified_symbol TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            exchange TEXT,
            name TEXT,
            currency TEXT,
            timezone TEXT,
            active BOOLEAN DEFAULT TRUE,
            first_seen_at TIMESTAMP,
            last_seen_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS symbol_provider_map (
            unified_symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            exchange TEXT,
            row_fetched_at TIMESTAMP,
            PRIMARY KEY (unified_symbol, provider, provider_symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS data_quality_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            snapshot_id TEXT,
            market TEXT,
            symbol TEXT,
            provider TEXT,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            retryable BOOLEAN DEFAULT FALSE,
            details TEXT,
            created_at TIMESTAMP NOT NULL
        )
        """,
    ]
    for statement in statements:
        con.execute(statement)
    _run_migrations(con)
    if own_connection:
        con.close()


def _run_migrations(con: duckdb.DuckDBPyConnection) -> None:
    applied = {
        int(row[0])
        for row in con.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for version, name in MIGRATIONS:
        if version in applied:
            continue
        if version == 1:
            _ensure_column(con, "pipeline_runs", "provider_summary", "TEXT")
            _ensure_column(con, "data_quality_events", "details", "TEXT")
        con.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, CURRENT_TIMESTAMP)",
            [version, name],
        )


def _ensure_column(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        str(row[1])
        for row in con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    }
    if column_name not in columns:
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def record_snapshot(snapshot: dict[str, Any]) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO data_snapshots
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot.get("snapshot_id"),
                snapshot.get("market"),
                snapshot.get("dataset"),
                snapshot.get("provider"),
                snapshot.get("snapshot_created_at"),
                snapshot.get("min_date"),
                snapshot.get("max_date"),
                snapshot.get("row_count"),
                snapshot.get("config_hash"),
            ],
        )


def record_run(run: dict[str, Any]) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO pipeline_runs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run.get("run_id"),
                run.get("task"),
                run.get("config_path"),
                run.get("config_hash"),
                run.get("snapshot_id"),
                run.get("data_range_start"),
                run.get("data_range_end"),
                run.get("provider_summary"),
                run.get("created_at"),
                run.get("finished_at"),
                run.get("status"),
                run.get("warning_count", 0),
                run.get("blocking_error_count", 0),
                run.get("report_path"),
                run.get("errors", "[]"),
            ],
        )


def record_quality_events(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    with connect() as con:
        con.executemany(
            """
            INSERT OR REPLACE INTO data_quality_events
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                [
                    event.get("event_id"),
                    event.get("run_id"),
                    event.get("snapshot_id"),
                    event.get("market"),
                    event.get("symbol"),
                    event.get("provider"),
                    event.get("event_type"),
                    event.get("severity"),
                    event.get("message"),
                    event.get("retryable", False),
                    event.get("details"),
                    event.get("created_at"),
                ]
                for event in events
            ],
        )
