from __future__ import annotations

import json
from pathlib import Path

from src.config import DATA_DIR, load_yaml
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
        events = con.execute(
            """
            SELECT event_type, severity, symbol, provider, message, retryable
            FROM data_quality_events
            WHERE run_id = ?
            ORDER BY created_at
            """,
            [run_id],
        ).fetchdf()
        provider_health = con.execute(
            """
            SELECT event_type, severity, market, symbol, provider, message, retryable
            FROM data_quality_events
            WHERE event_type = 'provider_health'
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchdf()
        cross_provider = con.execute(
            """
            SELECT event_type, severity, market, symbol, provider, message, retryable
            FROM data_quality_events
            WHERE event_type = 'cross_provider_check'
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchdf()
    if run.empty:
        raise ValueError(f"Unknown run_id: {run_id}")
    row = run.iloc[0].to_dict()
    config = _load_run_config(row.get("config_path"))
    provider_summary = _decode_json(row.get("provider_summary"))
    errors = _decode_json(row.get("errors"))
    quality_summary = "无结构化事件" if events.empty else _markdown_table(events.to_dict("records"))
    health_summary = (
        "暂无 provider health 事件"
        if provider_health.empty
        else _markdown_table(provider_health.to_dict("records"))
    )
    cross_summary = (
        "暂无 cross-provider check 事件"
        if cross_provider.empty
        else _markdown_table(cross_provider.to_dict("records"))
    )
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
- provider_summary: `{json.dumps(provider_summary, ensure_ascii=False, default=str)}`
- adjust: `{_config_value(config, "adjust", "见数据源默认口径")}`

## Strategy And Costs

- universe: `{config.get("universe")}`
- universe_mode: `{_config_value(config, "membership_mode", "见 configs/universes.yaml")}`
- strategy: `{json.dumps(config.get("strategy", {}), ensure_ascii=False, default=str)}`
- portfolio_semantics: `{_portfolio_semantics(config)}`
- benchmark: `{json.dumps(config.get("benchmark", {}), ensure_ascii=False, default=str)}`
- costs: `{json.dumps(config.get("costs", {}), ensure_ascii=False, default=str)}`
- turnover: `{row.get("turnover", "见回测结果")}`
- average_gross_exposure: `{row.get("average_gross_exposure", "见回测结果")}`
- total_cost_return: `{row.get("total_cost_return", "见回测结果")}`

## Quality And Errors

- errors: `{json.dumps(errors, ensure_ascii=False, default=str)}`

{quality_summary}

## Provider Health

{health_summary}

## Cross Provider Check

不判断真值，只提示不同数据源之间的差异。

{cross_summary}

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


def _decode_json(value: object) -> object:
    if not value:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _load_run_config(config_path: object) -> dict:
    if not config_path:
        return {}
    path = Path(str(config_path))
    if not path.exists():
        return {}
    return load_yaml(path)


def _config_value(config: dict, key: str, default: str) -> object:
    return config.get(key, default)


def _portfolio_semantics(config: dict) -> str:
    strategy = config.get("strategy", {})
    if strategy.get("type") == "ma_cross":
        return "固定 universe 等权预算；MA 信号为真才持有；未触发预算留现金，现金收益按 0 处理。"
    if strategy.get("type") == "etf_rotation":
        return "月末可得动量信号决定下一交易日持仓；top_n 标的等权。"
    return "见策略配置。"


def _markdown_table(rows: list[dict]) -> str:
    preferred = ["event_type", "severity", "market", "symbol", "provider", "message", "retryable"]
    columns = [column for column in preferred if any(column in row for row in rows)]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values = [str(row.get(column, "")).replace("|", "\\|") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
