from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"


def ensure_data_dirs() -> None:
    for path in [
        DATA_DIR / "raw",
        DATA_DIR / "processed" / "prices",
        DATA_DIR / "processed" / "fundamentals",
        DATA_DIR / "processed" / "index_components",
        DATA_DIR / "processed" / "calendars",
        DATA_DIR / "processed" / "corporate_actions",
        DATA_DIR / "factors",
        DATA_DIR / "screens",
        DATA_DIR / "backtests",
        DATA_DIR / "reports",
        DATA_DIR / "metadata",
        DATA_DIR / "logs",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def load_yaml(path: str | Path) -> dict[str, Any]:
    full_path = Path(path)
    if not full_path.is_absolute():
        full_path = PROJECT_ROOT / full_path
    with full_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {full_path}")
    return data


def list_yaml_files(path: str | Path) -> list[Path]:
    full_path = Path(path)
    if not full_path.is_absolute():
        full_path = PROJECT_ROOT / full_path
    return sorted(full_path.glob("*.yaml"))
