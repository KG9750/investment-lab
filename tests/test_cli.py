import json
import os
import subprocess
import sys

import pandas as pd
from typer.testing import CliRunner

from src.cli import app
from src.data_sources.base import PriceRequest, standardize_price_frame
from src.data_sources.provider_router import ProviderAttempt
from src.storage.duckdb_client import connect

runner = CliRunner()


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
        env=os.environ.copy(),
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
        env=os.environ.copy(),
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


def test_update_data_strict_records_symbol_failure_event() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "update-data",
            "--market",
            "CN",
            "--symbols",
            "SPY",
            "--start",
            "2024-01-01",
            "--strict",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode != 0
    assert payload["status"] == "error"
    assert payload["failed_symbol_count"] == 1
    assert any(error["type"] == "StrictUpdateError" for error in payload["errors"])
    with connect() as con:
        row = con.execute(
            """
            SELECT event_type, severity
            FROM data_quality_events
            WHERE run_id = ?
            """,
            [payload["run_id"]],
        ).fetchone()
    assert row == ("symbol_normalization_failed", "blocking")


def test_provider_health_records_structured_event(monkeypatch) -> None:
    class FakeRouter:
        def providers_for(self, market: str, dataset: str = "price") -> list[str]:
            return ["fake"]

        def get_price_from_provider(
            self,
            provider: str,
            request: PriceRequest,
            *,
            fallback_reason: str | None = None,
        ):
            attempt = ProviderAttempt(
                provider=provider,
                ok=True,
                message="ok",
                symbol=request.symbol,
                elapsed_ms=12,
                fallback_reason=fallback_reason,
            )
            return pd.DataFrame({"close": [1]}), attempt

        def summary(self, attempts: list[ProviderAttempt]) -> dict:
            return {"attempts": [attempt.__dict__ for attempt in attempts]}

    monkeypatch.setattr("src.cli.ProviderRouter", FakeRouter)
    result = runner.invoke(
        app,
        ["provider-health", "--mode", "quick", "--market", "US", "--output", "json"],
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert result.exit_code == 0
    assert payload["task"] == "provider-health"
    assert payload["matrix"][0]["status"] == "ok"
    with connect() as con:
        row = con.execute(
            """
            SELECT event_type, provider, details
            FROM data_quality_events
            WHERE run_id = ?
            """,
            [payload["run_id"]],
        ).fetchone()
    assert row[0] == "provider_health"
    assert row[1] == "fake"
    assert json.loads(row[2])["elapsed_ms"] == 12


def test_provider_health_dry_run_does_not_write_event(monkeypatch) -> None:
    class FakeRouter:
        def providers_for(self, market: str, dataset: str = "price") -> list[str]:
            return ["fake"]

        def get_price_from_provider(
            self,
            provider: str,
            request: PriceRequest,
            *,
            fallback_reason: str | None = None,
        ):
            return pd.DataFrame(), ProviderAttempt(
                provider=provider,
                ok=False,
                message="timeout",
                error_type="timeout",
                symbol=request.symbol,
                elapsed_ms=20,
                retryable=True,
            )

        def summary(self, attempts: list[ProviderAttempt]) -> dict:
            return {"attempts": [attempt.__dict__ for attempt in attempts]}

    monkeypatch.setattr("src.cli.ProviderRouter", FakeRouter)
    result = runner.invoke(
        app,
        [
            "provider-health",
            "--mode",
            "quick",
            "--market",
            "US",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert result.exit_code != 0
    assert payload["dry_run"] is True
    with connect() as con:
        count = con.execute("SELECT count(*) FROM data_quality_events").fetchone()[0]
    assert count == 0


def test_cross_provider_check_reports_close_diff(monkeypatch) -> None:
    def price(provider: str, close: float) -> pd.DataFrame:
        raw = pd.DataFrame(
            {
                "Date": ["2024-01-02"],
                "Open": [100],
                "High": [max(101, close)],
                "Low": [99],
                "Close": [close],
                "Volume": [1000],
            }
        )
        return standardize_price_frame(
            raw,
            request=PriceRequest("SPY", "US", "2024-01-01"),
            provider=provider,
            provider_symbol="SPY",
            adjust="raw",
        )

    class FakeRouter:
        def providers_for(self, market: str, dataset: str = "price") -> list[str]:
            return ["p1", "p2"]

        def get_price_from_provider(
            self,
            provider: str,
            request: PriceRequest,
            *,
            fallback_reason: str | None = None,
        ):
            frame = price(provider, 100 if provider == "p1" else 102)
            return frame, ProviderAttempt(provider=provider, ok=True, message="ok", symbol="SPY")

        def summary(self, attempts: list[ProviderAttempt]) -> dict:
            return {"attempts": [attempt.__dict__ for attempt in attempts]}

    monkeypatch.setattr("src.cli.ProviderRouter", FakeRouter)
    result = runner.invoke(
        app,
        [
            "cross-provider-check",
            "--market",
            "US",
            "--symbols",
            "SPY",
            "--close-threshold-pct",
            "0.5",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])

    assert result.exit_code == 0
    assert payload["task"] == "cross-provider-check"
    assert any(finding["category"] == "close_diff" for finding in payload["findings"])
    assert payload["note"] == "不判断真值，只提示不同数据源之间的差异。"
