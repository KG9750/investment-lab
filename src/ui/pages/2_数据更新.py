from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import load_yaml
from src.ui.chrome import inject_workbench_css, localize_table, page_header, status_band
from src.ui.cli_bridge import build_data_status_args, build_update_args, run_cli, stream_cli
from src.ui.state import recent_provider_health


def _try_json(line: str) -> dict | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _provider_health_hint(market: str) -> None:
    events = recent_provider_health(80)
    if events.empty:
        st.info("暂无数据源健康记录。可先到“数据源状态”页面运行 quick 检查。")
        return
    events = events[events["market"] == market].copy()
    if events.empty:
        st.info(f"暂无 {market} 市场的数据源健康记录。")
        return
    rows = []
    for provider, group in events.groupby("provider", sort=False):
        latest = group.sort_values("created_at").iloc[-1]
        details = _decode_details(latest.get("details"))
        rows.append(
            {
                "provider": provider,
                "status": "ok" if latest.get("severity") == "info" else "failed",
                "error_type": details.get("error_type"),
                "elapsed_ms": details.get("elapsed_ms"),
                "proxy_mode": details.get("proxy_mode"),
                "message": latest.get("message"),
            }
        )
    health = pd.DataFrame(rows)
    ok = health[health["status"] == "ok"]
    if ok.empty:
        st.warning("最近健康检查显示当前市场暂无可用数据源。建议尝试切换网络模式或稍后重试。")
    else:
        st.success("当前推荐数据源：" + ", ".join(ok["provider"].astype(str).tolist()))
    st.dataframe(localize_table(health), width="stretch", hide_index=True)


def _decode_details(value: object) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


inject_workbench_css()
page_header("数据更新", "数据源接入")

market = st.segmented_control("市场", ["CN", "HK", "US"], default="US")
_provider_health_hint(market)
default_symbols = {
    "CN": "000001.SZ,600000.SH",
    "HK": "0700.HK,9988.HK",
    "US": "SPY,QQQ",
}
universes = load_yaml("configs/universes.yaml")
market_universes = [
    key
    for key, value in universes.items()
    if value.get("market") == market and value.get("members")
]
source_mode = st.radio("来源", ["自定义标的", "股票池"], horizontal=True)
universe = None
symbols = None
if source_mode == "股票池" and market_universes:
    universe = st.selectbox("股票池", market_universes)
elif source_mode == "股票池":
    st.info("当前市场还没有配置静态股票池，请改用自定义标的。")
    symbols = st.text_input("标的", default_symbols[market], key=f"symbols_{market}")
else:
    symbols = st.text_input("标的", default_symbols[market], key=f"symbols_{market}")
control_cols = st.columns([1, 1])
start = control_cols[0].text_input("起始日期", "2018-01-01")
adjust = control_cols[1].selectbox(
    "复权口径",
    ["provider_default", "raw", "forward_adjusted", "backward_adjusted", "auto_adjusted"],
)
proxy_mode = st.selectbox(
    "网络模式",
    ["env", "direct"],
    help="env 使用当前代理环境；direct 临时直连。",
)

if st.button("检查本地增量状态"):
    try:
        status_args = build_data_status_args(market=market, symbols=symbols, universe=universe)
        result = run_cli(status_args)
        command = " ".join(["python", "-m", "src.cli", *status_args])
        st.markdown(
            f'<div class="command-strip">{command}</div>',
            unsafe_allow_html=True,
        )
        status_band(result.json_summary)
        if result.json_summary:
            metric_cols = st.columns(5)
            metric_cols[0].metric(
                "研究可用",
                result.json_summary.get("research_ready_symbol_count", 0),
            )
            metric_cols[1].metric(
                "过期",
                result.json_summary.get("stale_symbol_count", 0),
            )
            metric_cols[2].metric(
                "仅模拟",
                result.json_summary.get("synthetic_only_symbol_count", 0),
            )
            metric_cols[3].metric(
                "缺失",
                result.json_summary.get("missing_symbol_count", 0),
            )
            metric_cols[4].metric(
                "混合来源",
                result.json_summary.get("mixed_provider_symbol_count", 0),
            )
            status_rows = pd.DataFrame(result.json_summary.get("symbols", []))
            if not status_rows.empty:
                st.dataframe(localize_table(status_rows), width="stretch", hide_index=True)
    except Exception as exc:
        st.error(str(exc))

if st.button("运行更新"):
    try:
        args = build_update_args(
            market=market,
            symbols=symbols,
            universe=universe,
            start=start,
            adjust=adjust,
            strict=source_mode == "自定义标的",
            proxy_mode=proxy_mode,
        )
        st.markdown(
            f'<div class="command-strip">{" ".join(["python", "-m", "src.cli", *args])}</div>',
            unsafe_allow_html=True,
        )
        log = st.empty()
        lines: list[str] = []
        final_summary = None
        returncode = None
        for line in stream_cli(args):
            lines.append(line)
            log.code("".join(lines))
            payload = _try_json(line)
            if payload and "json_summary" in payload:
                final_summary = payload["json_summary"]
                returncode = payload.get("returncode")
        status_band(final_summary)
        st.write({"退出码": returncode})
        if final_summary:
            final_provider = final_summary.get("final_provider_by_symbol") or {}
            attempts = pd.DataFrame(final_summary.get("provider_attempts", []))
            if final_provider:
                st.subheader("最终数据源")
                st.dataframe(
                    localize_table(
                        pd.DataFrame(
                            [
                                {"symbol": symbol, "provider": provider}
                                for symbol, provider in final_provider.items()
                            ]
                        )
                    ),
                    width="stretch",
                    hide_index=True,
                )
            if not attempts.empty:
                st.subheader("数据源尝试链路")
                st.dataframe(localize_table(attempts), width="stretch", hide_index=True)
            if final_summary.get("failed_symbols"):
                st.subheader("失败标的")
                st.write(final_summary["failed_symbols"])
    except Exception as exc:
        st.error(str(exc))
