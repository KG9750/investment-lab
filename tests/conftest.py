from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_local_research_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("INVESTMENT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("INVESTMENT_DB_PATH", str(data_dir / "investment.duckdb"))
