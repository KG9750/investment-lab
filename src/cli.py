from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

from src.backtest.vectorbt_engine import run_backtest
from src.config import PROJECT_ROOT, ensure_data_dirs, load_yaml
from src.data_quality import run_price_quality_checks
from src.data_sources.base import PriceRequest
from src.data_sources.provider_router import ProviderRouter
from src.reporting.markdown_report import generate_markdown_report
from src.reporting.quantstats_report import generate_quantstats_html
from src.screening.screeners import run_screen
from src.screening.universe import get_universe_members
from src.storage.duckdb_client import init_db, record_run, record_snapshot
from src.storage.metadata import config_hash, make_run_id, make_snapshot_id, utc_now_str
from src.storage.parquet_store import ParquetStore
from src.symbols.normalize import normalize_symbol

app = typer.Typer(no_args_is_help=True)


def _base_summary(task: str, run_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "task": task,
        "run_id": run_id,
        "snapshot_id": None,
        "config_hash": None,
        "market": None,
        "dataset": None,
        "row_count": 0,
        "warning_count": 0,
        "blocking_error_count": 0,
        "report_path": None,
        "started_at": utc_now_str(),
        "finished_at": None,
        "errors": [],
    }


def _error(type_: str, message: str, severity: str = "blocking", **details: Any) -> dict[str, Any]:
    return {
        "type": type_,
        "message": message,
        "severity": severity,
        "symbol": details.pop("symbol", None),
        "provider": details.pop("provider", None),
        "retryable": details.pop("retryable", False),
        "details": details,
    }


def _emit(summary: dict[str, Any], output: str, exit_code: int = 0) -> None:
    summary["finished_at"] = summary.get("finished_at") or utc_now_str()
    if output == "json":
        typer.echo(json.dumps(summary, ensure_ascii=False, default=str))
    else:
        typer.echo(
            f"{summary['status']} task={summary['task']} run_id={summary.get('run_id')} "
            f"snapshot_id={summary.get('snapshot_id')} rows={summary.get('row_count')}"
        )
        if summary.get("errors"):
            typer.echo(json.dumps(summary["errors"], ensure_ascii=False, indent=2, default=str))
    if exit_code:
        raise SystemExit(exit_code)


def _fail(summary: dict[str, Any], exc: Exception, output: str) -> None:
    summary["status"] = "error"
    summary["blocking_error_count"] = max(int(summary.get("blocking_error_count", 0)), 1)
    summary["errors"].append(_error(type(exc).__name__, str(exc)))
    try:
        record_run(
            {
                "run_id": summary.get("run_id") or make_run_id(summary["task"], None, "failed"),
                "task": summary["task"],
                "config_hash": summary.get("config_hash"),
                "snapshot_id": summary.get("snapshot_id"),
                "created_at": summary.get("started_at"),
                "finished_at": utc_now_str(),
                "status": "error",
                "warning_count": summary.get("warning_count", 0),
                "blocking_error_count": summary.get("blocking_error_count", 1),
                "report_path": summary.get("report_path"),
                "errors": json.dumps(summary["errors"], ensure_ascii=False),
            }
        )
    except Exception as record_exc:
        summary["errors"].append(_error(type(record_exc).__name__, str(record_exc)))
    _emit(summary, output, exit_code=1)


@app.command("update-data")
def update_data(
    market: Annotated[str, typer.Option("--market")],
    symbols: Annotated[str | None, typer.Option("--symbols")] = None,
    universe: Annotated[str | None, typer.Option("--universe")] = None,
    start: Annotated[str, typer.Option("--start")] = "2018-01-01",
    end: Annotated[str | None, typer.Option("--end")] = None,
    adjust: Annotated[str, typer.Option("--adjust")] = "provider_default",
    resume: Annotated[bool, typer.Option("--resume")] = False,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    ensure_data_dirs()
    init_db()
    task_config = {
        "market": market,
        "symbols": symbols,
        "universe": universe,
        "start": start,
        "end": end,
        "adjust": adjust,
        "resume": resume,
    }
    run_id = make_run_id("update", market, "prices", task_config)
    snapshot_id = make_snapshot_id(market, "prices", task_config)
    summary = _base_summary("update-data", run_id)
    summary.update(
        {
            "snapshot_id": snapshot_id,
            "config_hash": config_hash(task_config),
            "market": market,
            "dataset": "prices",
        }
    )
    try:
        requested = _resolve_symbols(symbols, universe)
        router = ProviderRouter()
        store = ParquetStore()
        frames: list[pd.DataFrame] = []
        provider_attempts: list[dict[str, Any]] = []
        failed_symbols: list[str] = []
        for symbol in requested:
            unified = normalize_symbol(symbol, market, "manual")
            effective_start = _resume_start(store, market, unified, start) if resume else start
            request = PriceRequest(unified, market, effective_start, end, adjust, snapshot_id)
            df, attempts = router.get_price(request)
            provider_attempts.extend(router.summary(attempts)["attempts"])
            if df.empty:
                failed_symbols.append(unified)
                continue
            frames.append(df)
        prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        written = store.write_prices(prices, market)
        quality, _ = run_price_quality_checks(snapshot_id=snapshot_id, market=market)
        warnings = int((quality["severity"] == "warning").sum()) if not quality.empty else 0
        blocking = int((quality["severity"] == "blocking").sum()) if not quality.empty else 0
        summary.update(
            {
                "status": "ok" if blocking == 0 else "error",
                "row_count": int(len(prices)),
                "warning_count": warnings + len(failed_symbols),
                "blocking_error_count": blocking,
                "provider_summary": {
                    "attempts": provider_attempts,
                    "failed_symbols": failed_symbols,
                },
                "written_files": [str(path) for path in written],
            }
        )
        if failed_symbols:
            summary["errors"].append(
                _error(
                    "ProviderError",
                    "Some symbols failed",
                    severity="warning",
                    retryable=True,
                    failed_symbols=failed_symbols,
                )
            )
        if blocking:
            summary["errors"].append(
                _error(
                    "DataQualityError",
                    "Data quality check produced blocking findings",
                    severity="blocking",
                    market=market,
                    snapshot_id=snapshot_id,
                )
            )
        if not prices.empty:
            record_snapshot(
                {
                    "snapshot_id": snapshot_id,
                    "market": market,
                    "dataset": "prices",
                    "provider": ",".join(sorted(prices["provider"].unique())),
                    "snapshot_created_at": summary["started_at"],
                    "min_date": prices["date"].min(),
                    "max_date": prices["date"].max(),
                    "row_count": len(prices),
                    "config_hash": summary["config_hash"],
                }
            )
        record_run(
            {
                "run_id": run_id,
                "task": "update-data",
                "config_hash": summary["config_hash"],
                "snapshot_id": snapshot_id,
                "data_range_start": prices["date"].min() if not prices.empty else None,
                "data_range_end": prices["date"].max() if not prices.empty else None,
                "provider_summary": json.dumps(summary["provider_summary"], ensure_ascii=False),
                "created_at": summary["started_at"],
                "finished_at": utc_now_str(),
                "status": "ok" if blocking == 0 else "error",
                "warning_count": summary["warning_count"],
                "blocking_error_count": blocking,
                "errors": json.dumps(summary["errors"], ensure_ascii=False),
            }
        )
        _emit(summary, output, exit_code=1 if blocking else 0)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("data-quality")
def data_quality(
    snapshot_id: Annotated[str | None, typer.Option("--snapshot-id")] = None,
    market: Annotated[str | None, typer.Option("--market")] = None,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    run_id = make_run_id("quality", market, snapshot_id or "manual")
    summary = _base_summary("data-quality", run_id)
    summary.update({"snapshot_id": snapshot_id, "market": market, "dataset": "prices"})
    try:
        report, report_path = run_price_quality_checks(snapshot_id=snapshot_id, market=market)
        warnings = int((report["severity"] == "warning").sum()) if not report.empty else 0
        blocking = int((report["severity"] == "blocking").sum()) if not report.empty else 0
        summary.update(
            {
                "status": "ok" if blocking == 0 else "error",
                "row_count": int(len(report)),
                "warning_count": warnings,
                "blocking_error_count": blocking,
                "report_path": str(report_path) if report_path else None,
            }
        )
        if blocking:
            summary["errors"].append(
                _error(
                    "DataQualityError",
                    "Data quality check produced blocking findings",
                    severity="blocking",
                    market=market,
                    snapshot_id=snapshot_id,
                )
            )
        record_run(
            {
                "run_id": run_id,
                "task": "data-quality",
                "snapshot_id": snapshot_id,
                "created_at": summary["started_at"],
                "finished_at": utc_now_str(),
                "status": "ok" if blocking == 0 else "error",
                "warning_count": warnings,
                "blocking_error_count": blocking,
                "report_path": summary["report_path"],
                "errors": "[]",
            }
        )
        _emit(summary, output, exit_code=1 if blocking else 0)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("screen")
def screen(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    summary = _base_summary("screen")
    try:
        cfg = load_yaml(config)
        summary.update({"config_hash": config_hash(cfg), "market": cfg.get("market")})
        result, meta = run_screen(config)
        summary.update(
            {
                "run_id": meta["run_id"],
                "row_count": int(len(result)),
                "report_path": meta["path"],
                "snapshot_id": result["snapshot_id"].dropna().iloc[-1]
                if "snapshot_id" in result and not result.empty
                else None,
            }
        )
        record_run(
            {
                "run_id": meta["run_id"],
                "task": "screen",
                "config_path": str(config),
                "config_hash": summary["config_hash"],
                "snapshot_id": summary["snapshot_id"],
                "created_at": summary["started_at"],
                "finished_at": utc_now_str(),
                "status": "ok",
                "warning_count": 0,
                "blocking_error_count": 0,
                "report_path": meta["path"],
                "errors": "[]",
            }
        )
        _emit(summary, output)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("backtest")
def backtest(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    summary = _base_summary("backtest")
    try:
        cfg = load_yaml(config)
        summary.update({"config_hash": config_hash(cfg), "market": cfg.get("market")})
        result, meta = run_backtest(config)
        html = None
        if cfg.get("output", {}).get("quantstats", False):
            returns = pd.Series(
                result["strategy_return"].values,
                index=pd.to_datetime(result["date"]),
            )
            html = generate_quantstats_html(returns, meta["run_id"])
        summary.update(
            {
                "run_id": meta["run_id"],
                "row_count": int(len(result)),
                "report_path": str(html) if html else meta["path"],
                "total_return": meta["total_return"],
                "annual_return": meta["annual_return"],
                "max_drawdown": meta["max_drawdown"],
                "sharpe": meta["sharpe"],
                "turnover": meta["turnover"],
            }
        )
        record_run(
            {
                "run_id": meta["run_id"],
                "task": "backtest",
                "config_path": str(config),
                "config_hash": summary["config_hash"],
                "created_at": summary["started_at"],
                "finished_at": utc_now_str(),
                "status": "ok",
                "warning_count": 0,
                "blocking_error_count": 0,
                "report_path": summary["report_path"],
                "errors": "[]",
            }
        )
        _emit(summary, output)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("report")
def report(
    run_id: Annotated[str, typer.Option("--run-id")],
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    summary = _base_summary("report", run_id)
    try:
        path = generate_markdown_report(run_id)
        summary.update({"report_path": str(path), "row_count": 1})
        _emit(summary, output)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("compact")
def compact(
    dataset: Annotated[str, typer.Option("--dataset")] = "prices",
    market: Annotated[str | None, typer.Option("--market")] = None,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    run_id = make_run_id("compact", market, dataset)
    summary = _base_summary("compact", run_id)
    summary.update({"market": market, "dataset": dataset})
    try:
        if dataset != "prices":
            raise ValueError("Only prices compaction is implemented in phase one")
        row_count = ParquetStore().compact_prices(market=market)
        summary["row_count"] = row_count
        _emit(summary, output)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("ui")
def ui() -> None:
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "src/ui/streamlit_app.py"],
        cwd=PROJECT_ROOT,
        check=False,
    )


def _resolve_symbols(symbols: str | None, universe: str | None) -> list[str]:
    if symbols:
        return [item.strip() for item in symbols.split(",") if item.strip()]
    if universe:
        members = get_universe_members(universe)
        if members:
            return members
    raise ValueError("Either --symbols or --universe with members is required")


def _resume_start(store: ParquetStore, market: str, symbol: str, default_start: str) -> str:
    current = store.read_prices(market=market, symbols=[symbol])
    if current.empty:
        return default_start
    max_date = pd.to_datetime(current["date"]).max().date()
    return (pd.Timestamp(max_date) + pd.Timedelta(days=1)).date().isoformat()


if __name__ == "__main__":
    app()
