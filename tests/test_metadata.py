from src.storage.metadata import config_hash, make_run_id, make_snapshot_id


def test_ids_and_hash_are_stable_shape() -> None:
    cfg = {"market": "US", "symbols": ["SPY"]}
    assert config_hash(cfg) == config_hash({"symbols": ["SPY"], "market": "US"})
    snapshot_id = make_snapshot_id("US", "prices", cfg)
    run_id = make_run_id("backtest", "US", "demo", cfg)
    assert snapshot_id.startswith("US_prices_")
    assert "_demo_" in run_id
    assert snapshot_id.endswith(snapshot_id.split("_")[-1])
