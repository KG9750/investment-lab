from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def utc_now_str() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def short_hash(payload: Any, length: int = 8) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def config_hash(config: Any) -> str:
    return short_hash(config)


def make_snapshot_id(market: str, dataset: str, config: Any | None = None) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    suffix = short_hash({"config": config, "uuid": uuid.uuid4().hex}, 6)
    return f"{market}_{dataset}_{stamp}_{suffix}"


def make_run_id(task: str, market: str | None, name: str | None, config: Any | None = None) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    safe_market = market or "NA"
    safe_name = (name or "run").replace(" ", "_").replace("/", "_")
    suffix = short_hash({"config": config, "uuid": uuid.uuid4().hex}, 6)
    return f"{task}_{safe_market}_{safe_name}_{stamp}_{suffix}"


def read_jsonl_last(path: str | Path) -> dict[str, Any] | None:
    full_path = Path(path)
    if not full_path.exists():
        return None
    last: dict[str, Any] | None = None
    with full_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                last = json.loads(line)
    return last
