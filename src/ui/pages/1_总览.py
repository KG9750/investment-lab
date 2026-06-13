from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ui.chrome import inject_workbench_css, localize_table, page_header, render_empty
from src.ui.cli_bridge import build_data_status_args, run_cli
from src.ui.state import (
    recent_cross_provider_checks,
    recent_provider_health,
    recent_quality_events,
    recent_runs,
    recent_snapshots,
)

inject_workbench_css()
page_header("总览", "运行台账")

snapshots = recent_snapshots()
runs = recent_runs()
events = recent_quality_events()
health_events = recent_provider_health()
cross_events = recent_cross_provider_checks()

cols = st.columns(4)
cols[0].metric("数据快照", len(snapshots))
cols[1].metric("运行记录", len(runs))
cols[2].metric("质量事件", len(events))
cols[3].metric(
    "阻断错误",
    int(runs["blocking_error_count"].fillna(0).sum()) if not runs.empty else 0,
)

provider_cols = st.columns(4)
provider_cols[0].metric("数据源健康事件", len(health_events))
provider_cols[1].metric(
    "最近健康失败",
    int((health_events["severity"] != "info").sum()) if not health_events.empty else 0,
)
provider_cols[2].metric("一致性事件", len(cross_events))
provider_cols[3].metric(
    "Fallback 次数",
    int(
        runs["provider_summary"].fillna("").str.contains("fallback_reason").sum()
    )
    if not runs.empty and "provider_summary" in runs
    else 0,
)

st.subheader("数据可用性")
if st.button("检查 CN_REAL_CORE"):
    result = run_cli(build_data_status_args(market="CN", universe="CN_REAL_CORE"))
    if result.json_summary:
        cols = st.columns(5)
        cols[0].metric("研究可用", result.json_summary.get("research_ready_symbol_count", 0))
        cols[1].metric("过期", result.json_summary.get("stale_symbol_count", 0))
        cols[2].metric("仅模拟", result.json_summary.get("synthetic_only_symbol_count", 0))
        cols[3].metric("缺失", result.json_summary.get("missing_symbol_count", 0))
        cols[4].metric("混合来源", result.json_summary.get("mixed_provider_symbol_count", 0))
        status_rows = pd.DataFrame(result.json_summary.get("symbols", []))
        if not status_rows.empty:
            st.dataframe(localize_table(status_rows), width="stretch", hide_index=True)
    else:
        st.error(result.stderr or result.stdout or "data-status 未返回 JSON。")

st.subheader("数据快照")
if snapshots.empty:
    render_empty("暂无快照。先在数据更新页面抓取本地行情。")
else:
    st.dataframe(localize_table(snapshots), width="stretch", hide_index=True)

st.subheader("运行记录")
if runs.empty:
    render_empty("暂无运行记录。")
else:
    st.dataframe(localize_table(runs), width="stretch", hide_index=True)

st.subheader("质量事件")
if events.empty:
    render_empty("暂无质量事件。")
else:
    st.dataframe(localize_table(events), width="stretch", hide_index=True)

st.subheader("最近数据源健康")
if health_events.empty:
    render_empty("暂无数据源健康事件。")
else:
    st.dataframe(localize_table(health_events), width="stretch", hide_index=True)

st.subheader("最近数据一致性")
if cross_events.empty:
    render_empty("暂无数据一致性事件。")
else:
    st.dataframe(localize_table(cross_events), width="stretch", hide_index=True)
