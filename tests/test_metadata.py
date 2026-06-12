from src.storage.duckdb_client import connect, init_db
from src.storage.metadata import config_hash, make_run_id, make_snapshot_id


def test_ids_and_hash_are_stable_shape() -> None:
    cfg = {"market": "US", "symbols": ["SPY"]}
    assert config_hash(cfg) == config_hash({"symbols": ["SPY"], "market": "US"})
    snapshot_id = make_snapshot_id("US", "prices", cfg)
    run_id = make_run_id("backtest", "US", "demo", cfg)
    assert snapshot_id.startswith("US_prices_")
    assert "_demo_" in run_id
    assert snapshot_id.endswith(snapshot_id.split("_")[-1])


def test_schema_migrations_are_idempotent() -> None:
    init_db()
    init_db()
    with connect() as con:
        rows = con.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        details_column = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'data_quality_events' AND column_name = 'details'"
        ).fetchone()

    assert rows == [(1, "ensure_observability_columns")]
    assert details_column == ("details",)
