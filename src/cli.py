from __future__ import annotations

import json
import subprocess
import sys
import uuid
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
from src.storage.duckdb_client import (
    connect,
    init_db,
    record_quality_events,
    record_run,
    record_snapshot,
)
from src.storage.metadata import config_hash, make_run_id, make_snapshot_id, utc_now_str
from src.storage.parquet_store import ParquetStore, next_resume_start, price_status
from src.symbols.normalize import normalize_symbol

app = typer.Typer(no_args_is_help=True)

HEALTH_SAMPLES = {
    "quick": {
        "CN": ["000001.SZ"],
        "HK": ["0700.HK"],
        "US": ["SPY"],
    },
    "full": {
        "CN": ["000001.SZ", "600000.SH", "000858.SZ"],
        "HK": ["0700.HK", "9988.HK"],
        "US": ["SPY", "QQQ", "AAPL"],
    },
}
MARKETS = ["CN", "HK", "US"]


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


def _event(
    *,
    run_id: str,
    snapshot_id: str | None,
    market: str | None,
    event_type: str,
    severity: str,
    message: str,
    symbol: str | None = None,
    provider: str | None = None,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "market": market,
        "symbol": symbol,
        "provider": provider,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "retryable": retryable,
        "details": json.dumps(details or {}, ensure_ascii=False, default=str),
        "created_at": utc_now_str(),
    }


def _quality_report_events(
    report: pd.DataFrame,
    *,
    run_id: str,
    snapshot_id: str | None,
    market: str | None,
) -> list[dict[str, Any]]:
    if report.empty:
        return []
    events: list[dict[str, Any]] = []
    for row in report.to_dict("records"):
        check_type = str(row.get("check_type"))
        affected_rows = row.get("affected_rows")
        events.append(
            _event(
                run_id=run_id,
                snapshot_id=row.get("snapshot_id") or snapshot_id,
                market=row.get("market") or market,
                symbol=row.get("symbol"),
                event_type=check_type,
                severity=str(row.get("severity") or "warning"),
                message=str(row.get("message") or check_type),
                retryable=False,
                details={
                    "affected_rows": affected_rows,
                    "check_type": check_type,
                    "source": "data_quality",
                },
            )
        )
    return events


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


def _default_recent_start(days: int = 30) -> str:
    return (pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=days)).date().isoformat()


def _default_today() -> str:
    return pd.Timestamp.now("UTC").normalize().date().isoformat()


def _providers_for_targets(
    router: ProviderRouter,
    *,
    market: str | None,
    provider: str | None = None,
) -> list[tuple[str, str]]:
    markets = [market] if market else MARKETS
    targets: list[tuple[str, str]] = []
    for target_market in markets:
        enabled = router.providers_for(target_market, "price")
        for target_provider in enabled:
            if provider and target_provider != provider:
                continue
            targets.append((target_market, target_provider))
    return targets


def _get_provider_attempts(
    router: Any,
    provider: str,
    request: PriceRequest,
    *,
    fallback_reason: str | None = None,
) -> tuple[pd.DataFrame, list[Any]]:
    if hasattr(router, "get_price_from_provider_attempts"):
        return router.get_price_from_provider_attempts(
            provider,
            request,
            fallback_reason=fallback_reason,
        )
    df, attempt = router.get_price_from_provider(
        provider,
        request,
        fallback_reason=fallback_reason,
    )
    return df, [attempt]


def _attempt_to_event_details(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": attempt.get("ok"),
        "error_type": attempt.get("error_type"),
        "elapsed_ms": attempt.get("elapsed_ms"),
        "fallback_reason": attempt.get("fallback_reason"),
        "proxy_mode": attempt.get("proxy_mode"),
        "attempt_number": attempt.get("attempt_number"),
    }


def _validate_proxy_mode(proxy_mode: str | None) -> None:
    if proxy_mode is not None and proxy_mode not in {"env", "direct"}:
        raise ValueError("proxy-mode must be env or direct")


def _provider_health_matrix(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for attempt in attempts:
        key = (str(attempt.get("market")), str(attempt.get("provider")))
        buckets.setdefault(key, []).append(attempt)
    rows: list[dict[str, Any]] = []
    for (market, provider), items in sorted(buckets.items()):
        ok_count = sum(1 for item in items if item.get("ok"))
        elapsed = [int(item.get("elapsed_ms") or 0) for item in items]
        failures = [item for item in items if not item.get("ok")]
        rows.append(
            {
                "market": market,
                "provider": provider,
                "status": "ok" if ok_count else "failed",
                "ok_count": ok_count,
                "failed_count": len(items) - ok_count,
                "avg_elapsed_ms": round(sum(elapsed) / len(elapsed), 1) if elapsed else 0,
                "error_types": sorted(
                    {
                        str(item.get("error_type"))
                        for item in failures
                        if item.get("error_type")
                    }
                ),
                "retryable": any(bool(item.get("retryable")) for item in failures),
                "last_message": failures[-1].get("message") if failures else "ok",
            }
        )
    return rows


def _cross_provider_findings(
    symbol: str,
    frames: list[pd.DataFrame],
    *,
    close_threshold_pct: float,
) -> list[dict[str, Any]]:
    if len(frames) < 2:
        return [
            {
                "category": "insufficient_providers",
                "symbol": symbol,
                "message": "需要至少两个成功数据源才能比较。",
            }
        ]
    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"]).dt.date.astype(str)
    findings: list[dict[str, Any]] = []

    row_counts = combined.groupby("provider").size().to_dict()
    if row_counts and max(row_counts.values()) != min(row_counts.values()):
        findings.append(
            {
                "category": "row_count_diff",
                "symbol": symbol,
                "message": "不同 provider 返回行数不一致。",
                "row_counts": row_counts,
            }
        )

    all_dates = set(combined["date"].unique())
    for provider, group in combined.groupby("provider"):
        missing = sorted(all_dates - set(group["date"].unique()))
        if missing:
            findings.append(
                {
                    "category": "missing_dates",
                    "symbol": symbol,
                    "provider": provider,
                    "message": f"{provider} 缺少 {len(missing)} 个日期。",
                    "missing_dates": missing,
                }
            )

    bad_ohlc = combined[
        (combined["open"] <= 0)
        | (combined["high"] <= 0)
        | (combined["low"] <= 0)
        | (combined["close"] <= 0)
        | (combined["high"] < combined["low"])
        | (combined["high"] < combined["open"])
        | (combined["high"] < combined["close"])
        | (combined["low"] > combined["open"])
        | (combined["low"] > combined["close"])
    ]
    for row in bad_ohlc.to_dict("records"):
        findings.append(
            {
                "category": "ohlc_anomaly",
                "symbol": symbol,
                "provider": row.get("provider"),
                "date": row.get("date"),
                "message": "OHLC 字段不满足基本价格关系。",
            }
        )

    close_table = combined.pivot_table(
        index="date",
        columns="provider",
        values="close",
        aggfunc="last",
    )
    for date, row in close_table.iterrows():
        values = row.dropna()
        if len(values) < 2:
            continue
        min_close = float(values.min())
        max_close = float(values.max())
        if min_close <= 0:
            continue
        diff_pct = (max_close - min_close) / min_close * 100
        if diff_pct > close_threshold_pct:
            findings.append(
                {
                    "category": "close_diff",
                    "symbol": symbol,
                    "date": date,
                    "message": f"close 差异 {diff_pct:.2f}% 超过阈值。",
                    "diff_pct": round(diff_pct, 4),
                    "closes": {
                        str(provider): float(close)
                        for provider, close in values.to_dict().items()
                    },
                }
            )
    return findings


def _fail(summary: dict[str, Any], exc: Exception, output: str) -> None:
    summary["status"] = "error"
    summary["run_id"] = summary.get("run_id") or make_run_id(summary["task"], None, "failed")
    summary["blocking_error_count"] = max(int(summary.get("blocking_error_count", 0)), 1)
    summary["errors"].append(_error(type(exc).__name__, str(exc)))
    try:
        record_run(
            {
                "run_id": summary["run_id"],
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
    strict: Annotated[bool, typer.Option("--strict")] = False,
    proxy_mode: Annotated[str | None, typer.Option("--proxy-mode")] = None,
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
        "strict": strict,
        "proxy_mode": proxy_mode,
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
            "proxy_mode": proxy_mode or "config",
        }
    )
    try:
        requested = _resolve_symbols(symbols, universe)
        _validate_proxy_mode(proxy_mode)
        router = ProviderRouter(proxy_mode=proxy_mode)
        store = ParquetStore()
        frames: list[pd.DataFrame] = []
        provider_attempts: list[dict[str, Any]] = []
        failed_symbols: list[str] = []
        succeeded_symbols: list[str] = []
        final_provider_by_symbol: dict[str, str] = {}
        events: list[dict[str, Any]] = []
        for symbol in requested:
            try:
                unified = normalize_symbol(symbol, market, "manual")
            except ValueError as exc:
                failed_symbols.append(symbol)
                events.append(
                    _event(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        market=market,
                        symbol=symbol,
                        event_type="symbol_normalization_failed",
                        severity="blocking" if strict else "warning",
                        message=str(exc),
                        retryable=False,
                    )
                )
                continue
            effective_start = _resume_start(store, market, unified, start) if resume else start
            request = PriceRequest(unified, market, effective_start, end, adjust, snapshot_id)
            df, attempts = router.get_price(request)
            attempt_summary = router.summary(attempts)["attempts"]
            provider_attempts.extend(
                [{**attempt, "symbol": unified} for attempt in attempt_summary]
            )
            for attempt in attempt_summary:
                ok = bool(attempt["ok"])
                events.append(
                    _event(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        market=market,
                        symbol=unified,
                        provider=attempt["provider"],
                        event_type="provider_attempt",
                        severity="info" if ok else "warning",
                        message=attempt.get("message") or "ok",
                        retryable=bool(attempt.get("retryable")),
                        details=_attempt_to_event_details(attempt),
                    )
                )
            if df.empty:
                failed_symbols.append(unified)
                continue
            succeeded_symbols.append(unified)
            final_provider_by_symbol[unified] = str(df["provider"].dropna().iloc[-1])
            frames.append(df)
        prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        written = store.write_prices(prices, market)
        quality, _ = run_price_quality_checks(snapshot_id=snapshot_id, market=market)
        events.extend(
            _quality_report_events(
                quality,
                run_id=run_id,
                snapshot_id=snapshot_id,
                market=market,
            )
        )
        warnings = int((quality["severity"] == "warning").sum()) if not quality.empty else 0
        quality_blocking = (
            int((quality["severity"] == "blocking").sum()) if not quality.empty else 0
        )
        strict_failure = strict and bool(failed_symbols)
        blocking = quality_blocking + (1 if strict_failure else 0)
        summary.update(
            {
                "status": "ok" if blocking == 0 else "error",
                "row_count": int(len(prices)),
                "warning_count": warnings + len(failed_symbols),
                "blocking_error_count": blocking,
                "requested_symbol_count": len(requested),
                "succeeded_symbol_count": len(succeeded_symbols),
                "failed_symbol_count": len(failed_symbols),
                "requested_symbols": requested,
                "succeeded_symbols": succeeded_symbols,
                "failed_symbols": failed_symbols,
                "final_provider_by_symbol": final_provider_by_symbol,
                "provider_attempts": provider_attempts,
                "fallback_count": sum(
                    1
                    for attempt in provider_attempts
                    if attempt.get("ok") and attempt.get("fallback_reason")
                ),
                "strict": strict,
                "provider_summary": {
                    "attempts": provider_attempts,
                    "failed_symbols": failed_symbols,
                    "final_provider_by_symbol": final_provider_by_symbol,
                },
                "written_files": [str(path) for path in written],
            }
        )
        record_quality_events(events)
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
        if strict_failure:
            summary["errors"].append(
                _error(
                    "StrictUpdateError",
                    "Strict mode failed because some symbols could not be fetched",
                    severity="blocking",
                    failed_symbols=failed_symbols,
                )
            )
        if quality_blocking:
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
        record_quality_events(
            _quality_report_events(
                report,
                run_id=run_id,
                snapshot_id=snapshot_id,
                market=market,
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
                "errors": json.dumps(summary["errors"], ensure_ascii=False),
            }
        )
        _emit(summary, output, exit_code=1 if blocking else 0)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("data-status")
def data_status(
    market: Annotated[str, typer.Option("--market")],
    symbols: Annotated[str | None, typer.Option("--symbols")] = None,
    universe: Annotated[str | None, typer.Option("--universe")] = None,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    run_id = make_run_id("data_status", market, symbols or universe or "manual")
    summary = _base_summary("data-status", run_id)
    summary.update({"market": market, "dataset": "prices"})
    try:
        requested = [
            normalize_symbol(item, market, "manual")
            for item in _resolve_symbols(symbols, universe)
        ]
        prices = ParquetStore().read_prices(market=market, symbols=requested)
        rows = price_status(prices, market=market, requested_symbols=requested)
        available = sum(1 for row in rows if row["row_count"] > 0)
        research_ready = sum(1 for row in rows if row["status"] == "ready")
        summary.update(
            {
                "row_count": int(sum(row["row_count"] for row in rows)),
                "symbol_count": len(rows),
                "available_symbol_count": available,
                "research_ready_symbol_count": research_ready,
                "missing_symbol_count": len(rows) - available,
                "stale_symbol_count": sum(1 for row in rows if row["status"] == "stale"),
                "synthetic_only_symbol_count": sum(
                    1 for row in rows if row["status"] == "synthetic_only"
                ),
                "mixed_provider_symbol_count": sum(
                    1 for row in rows if row["status"] == "mixed_provider"
                ),
                "symbols": rows,
            }
        )
        _emit(summary, output)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("provider-health")
def provider_health(
    mode: Annotated[str, typer.Option("--mode")] = "quick",
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    market: Annotated[str | None, typer.Option("--market")] = None,
    proxy_mode: Annotated[str | None, typer.Option("--proxy-mode")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    init_db()
    task_config = {
        "mode": mode,
        "provider": provider,
        "market": market,
        "proxy_mode": proxy_mode,
        "dry_run": dry_run,
    }
    run_id = make_run_id("provider_health", market or "ALL", mode, task_config)
    summary = _base_summary("provider-health", run_id)
    summary.update(
        {
            "config_hash": config_hash(task_config),
            "market": market,
            "dataset": "provider_health",
            "dry_run": dry_run,
            "mode": mode,
            "proxy_mode": proxy_mode or "config",
        }
    )
    try:
        if mode not in HEALTH_SAMPLES:
            raise ValueError("mode must be quick or full")
        _validate_proxy_mode(proxy_mode)
        router = ProviderRouter(proxy_mode=proxy_mode)
        targets = _providers_for_targets(router, market=market, provider=provider)
        if not targets:
            raise ValueError("No enabled provider targets matched the request")

        attempts: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        start = _default_recent_start()
        end = _default_today()
        for target_market, target_provider in targets:
            for symbol in HEALTH_SAMPLES[mode][target_market]:
                unified = normalize_symbol(symbol, target_market, "manual")
                request = PriceRequest(
                    unified,
                    target_market,
                    start,
                    end,
                    "provider_default",
                    timeout_seconds=5,
                )
                _, provider_attempts = _get_provider_attempts(router, target_provider, request)
                for attempt in provider_attempts:
                    attempt_row = router.summary([attempt])["attempts"][0]
                    attempt_row["market"] = target_market
                    attempts.append(attempt_row)
                    events.append(
                        _event(
                            run_id=run_id,
                            snapshot_id=None,
                            market=target_market,
                            symbol=unified,
                            provider=target_provider,
                            event_type="provider_health",
                            severity="info" if attempt.ok else "warning",
                            message=attempt.message or ("ok" if attempt.ok else "failed"),
                            retryable=attempt.retryable,
                            details=_attempt_to_event_details(attempt_row),
                        )
                    )

        ok_count = sum(1 for attempt in attempts if attempt.get("ok"))
        failed_count = len(attempts) - ok_count
        matrix = _provider_health_matrix(attempts)
        blocking = 1 if ok_count == 0 else 0
        summary.update(
            {
                "status": "ok" if blocking == 0 else "error",
                "row_count": len(attempts),
                "warning_count": failed_count,
                "blocking_error_count": blocking,
                "attempts": attempts,
                "matrix": matrix,
                "ok_count": ok_count,
                "failed_count": failed_count,
            }
        )
        if not dry_run:
            record_quality_events(events)
            record_run(
                {
                    "run_id": run_id,
                    "task": "provider-health",
                    "config_hash": summary["config_hash"],
                    "provider_summary": json.dumps(
                        {"attempts": attempts, "matrix": matrix},
                        ensure_ascii=False,
                        default=str,
                    ),
                    "created_at": summary["started_at"],
                    "finished_at": utc_now_str(),
                    "status": summary["status"],
                    "warning_count": failed_count,
                    "blocking_error_count": blocking,
                    "errors": json.dumps(summary["errors"], ensure_ascii=False),
                }
            )
        _emit(summary, output, exit_code=1 if blocking else 0)
    except Exception as exc:
        _fail(summary, exc, output)


@app.command("cross-provider-check")
def cross_provider_check(
    market: Annotated[str, typer.Option("--market")],
    symbols: Annotated[str, typer.Option("--symbols")],
    start: Annotated[str, typer.Option("--start")] = "2024-01-01",
    end: Annotated[str | None, typer.Option("--end")] = None,
    close_threshold_pct: Annotated[float, typer.Option("--close-threshold-pct")] = 0.5,
    proxy_mode: Annotated[str | None, typer.Option("--proxy-mode")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    output: Annotated[str, typer.Option("--output")] = "text",
) -> None:
    init_db()
    task_config = {
        "market": market,
        "symbols": symbols,
        "start": start,
        "end": end,
        "close_threshold_pct": close_threshold_pct,
        "proxy_mode": proxy_mode,
        "dry_run": dry_run,
    }
    run_id = make_run_id("cross_provider", market, symbols, task_config)
    summary = _base_summary("cross-provider-check", run_id)
    summary.update(
        {
            "config_hash": config_hash(task_config),
            "market": market,
            "dataset": "cross_provider_check",
            "dry_run": dry_run,
            "proxy_mode": proxy_mode or "config",
        }
    )
    try:
        _validate_proxy_mode(proxy_mode)
        router = ProviderRouter(proxy_mode=proxy_mode)
        providers = router.providers_for(market, "price")
        if len(providers) < 2:
            raise ValueError(f"At least two enabled providers are required for {market}")

        attempts: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        for raw_symbol in _resolve_symbols(symbols, None):
            unified = normalize_symbol(raw_symbol, market, "manual")
            frames: list[pd.DataFrame] = []
            for provider in providers:
                request = PriceRequest(
                    unified,
                    market,
                    start,
                    end,
                    "provider_default",
                    timeout_seconds=8,
                )
                df, provider_attempts = _get_provider_attempts(router, provider, request)
                for attempt in provider_attempts:
                    attempt_row = router.summary([attempt])["attempts"][0]
                    attempt_row["market"] = market
                    attempts.append(attempt_row)
                    events.append(
                        _event(
                            run_id=run_id,
                            snapshot_id=None,
                            market=market,
                            symbol=unified,
                            provider=provider,
                            event_type="cross_provider_check",
                            severity="info" if attempt.ok else "warning",
                            message=attempt.message or ("ok" if attempt.ok else "failed"),
                            retryable=attempt.retryable,
                            details={
                                "category": "provider_attempt",
                                **_attempt_to_event_details(attempt_row),
                            },
                        )
                    )
                if not df.empty:
                    frames.append(df)
            symbol_findings = _cross_provider_findings(
                unified,
                frames,
                close_threshold_pct=close_threshold_pct,
            )
            findings.extend(symbol_findings)
            for finding in symbol_findings:
                events.append(
                    _event(
                        run_id=run_id,
                        snapshot_id=None,
                        market=market,
                        symbol=unified,
                        provider=finding.get("provider"),
                        event_type="cross_provider_check",
                        severity="warning",
                        message=str(finding.get("message")),
                        retryable=False,
                        details=finding,
                    )
                )

        ok_attempts = [attempt for attempt in attempts if attempt.get("ok")]
        blocking = 1 if not ok_attempts else 0
        warning_count = len(findings) + sum(1 for attempt in attempts if not attempt.get("ok"))
        summary.update(
            {
                "status": "ok" if blocking == 0 else "error",
                "row_count": len(findings),
                "warning_count": warning_count,
                "blocking_error_count": blocking,
                "attempts": attempts,
                "findings": findings,
                "close_threshold_pct": close_threshold_pct,
                "note": "不判断真值，只提示不同数据源之间的差异。",
            }
        )
        if not dry_run:
            record_quality_events(events)
            record_run(
                {
                    "run_id": run_id,
                    "task": "cross-provider-check",
                    "config_hash": summary["config_hash"],
                    "provider_summary": json.dumps(
                        {"attempts": attempts, "findings": findings},
                        ensure_ascii=False,
                        default=str,
                    ),
                    "created_at": summary["started_at"],
                    "finished_at": utc_now_str(),
                    "status": summary["status"],
                    "warning_count": warning_count,
                    "blocking_error_count": blocking,
                    "errors": json.dumps(summary["errors"], ensure_ascii=False),
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
        summary.update(
            {
                "run_id": make_run_id("screen", cfg.get("market"), cfg.get("name"), cfg),
                "config_hash": config_hash(cfg),
                "market": cfg.get("market"),
            }
        )
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
        summary.update(
            {
                "run_id": make_run_id("backtest", cfg.get("market"), cfg.get("name"), cfg),
                "config_hash": config_hash(cfg),
                "market": cfg.get("market"),
            }
        )
        result, meta = run_backtest(config)
        html = None
        returns = pd.Series(
            result["strategy_return"].values,
            index=pd.to_datetime(result["date"]),
        )
        if cfg.get("output", {}).get("quantstats", False) and returns.abs().sum() > 0:
            html = generate_quantstats_html(returns, meta["run_id"])
        summary.update(
            {
                "run_id": meta["run_id"],
                "snapshot_id": meta.get("snapshot_id"),
                "row_count": int(len(result)),
                "result_path": meta["path"],
                "report_path": str(html) if html else meta["path"],
                "data_range_start": meta.get("data_range_start"),
                "data_range_end": meta.get("data_range_end"),
                "provider_summary": meta.get("provider_summary", {}),
                "total_return": meta["total_return"],
                "annual_return": meta["annual_return"],
                "max_drawdown": meta["max_drawdown"],
                "sharpe": meta["sharpe"],
                "turnover": meta["turnover"],
                "average_gross_exposure": meta.get("average_gross_exposure"),
                "total_cost_return": meta.get("total_cost_return"),
            }
        )
        record_run(
            {
                "run_id": meta["run_id"],
                "task": "backtest",
                "config_path": str(config),
                "config_hash": summary["config_hash"],
                "snapshot_id": meta.get("snapshot_id"),
                "data_range_start": meta.get("data_range_start"),
                "data_range_end": meta.get("data_range_end"),
                "provider_summary": json.dumps(
                    meta.get("provider_summary", {}),
                    ensure_ascii=False,
                    default=str,
                ),
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
        with connect(read_only=False) as con:
            run = con.execute(
                "SELECT snapshot_id, config_hash FROM pipeline_runs WHERE run_id = ?",
                [run_id],
            ).fetchone()
        summary.update(
            {
                "snapshot_id": run[0] if run else None,
                "config_hash": run[1] if run else None,
                "report_path": str(path),
                "row_count": 1,
            }
        )
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
        [sys.executable, "-m", "streamlit", "run", "src/ui/投资研究台.py"],
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
    return next_resume_start(market, max_date)


if __name__ == "__main__":
    app()
