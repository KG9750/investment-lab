from __future__ import annotations

from pathlib import Path

from src.config import DATA_DIR
from src.storage.duckdb_client import connect
from src.storage.metadata import utc_now_str

LIMITATIONS = (
    "阶段一结果仅用于研究，不构成投资建议。A 股涨跌停、停牌、T+1、ST、退市、"
    "公司行动和历史指数成分股时点修正在本阶段未完整建模。"
)


def generate_markdown_report(run_id: str) -> Path:
    with connect(read_only=False) as con:
        run = con.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?",
            [run_id],
        ).fetchdf()
    if run.empty:
        raise ValueError(f"Unknown run_id: {run_id}")
    row = run.iloc[0].to_dict()
    report_path = DATA_DIR / "reports" / f"{run_id}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Investment Research Report

Generated at: {utc_now_str()}

## Traceability

- run_id: `{row.get("run_id")}`
- task: `{row.get("task")}`
- snapshot_id: `{row.get("snapshot_id")}`
- config_hash: `{row.get("config_hash")}`
- status: `{row.get("status")}`
- warning_count: `{row.get("warning_count")}`
- blocking_error_count: `{row.get("blocking_error_count")}`

## Data

- data_range_start: `{row.get("data_range_start")}`
- data_range_end: `{row.get("data_range_end")}`
- provider_summary: `{row.get("provider_summary")}`

## Research Use Only

{LIMITATIONS}
"""
    report_path.write_text(content, encoding="utf-8")
    with connect() as con:
        con.execute(
            "UPDATE pipeline_runs SET report_path = ? WHERE run_id = ?",
            [str(report_path), run_id],
        )
    return report_path
