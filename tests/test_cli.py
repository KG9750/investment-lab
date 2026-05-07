import json
import subprocess
import sys

from src.storage.duckdb_client import connect


def test_cli_json_failure_contract() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "screen",
            "--config",
            "configs/screens/does_not_exist.yaml",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode != 0
    assert payload["status"] == "error"
    assert payload["task"] == "screen"
    assert payload["errors"]


def test_data_quality_persists_errors() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "data-quality",
            "--snapshot-id",
            "missing_snapshot_for_test",
            "--market",
            "US",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode != 0
    assert payload["errors"]
    with connect() as con:
        stored = con.execute(
            "SELECT errors FROM pipeline_runs WHERE run_id = ?",
            [payload["run_id"]],
        ).fetchone()[0]
    assert json.loads(stored)
