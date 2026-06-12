from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ui.chrome import inject_workbench_css, localize_table, page_header, render_empty
from src.ui.state import recent_quality_events, recent_runs, recent_snapshots

st.set_page_config(page_title="投资研究台", layout="wide")
inject_workbench_css()
page_header("投资研究台", "本地研究工作台")

snapshots = recent_snapshots()
runs = recent_runs()
events = recent_quality_events()

metric_cols = st.columns(4)
metric_cols[0].metric("数据快照", len(snapshots))
metric_cols[1].metric("最近运行", len(runs))
metric_cols[2].metric(
    "警告",
    int(runs["warning_count"].fillna(0).sum()) if not runs.empty else 0,
)
metric_cols[3].metric(
    "阻断错误",
    int(runs["blocking_error_count"].fillna(0).sum()) if not runs.empty else 0,
)

left, right = st.columns([1, 1])
with left:
    st.subheader("最近数据快照")
    if snapshots.empty:
        command = (
            "python -m src.cli update-data --market US --symbols SPY,QQQ "
            "--start 2018-01-01 --resume --output json"
        )
        render_empty(
            "还没有本地数据快照。先运行一次数据更新。",
            command,
        )
    else:
        st.dataframe(localize_table(snapshots), width="stretch", hide_index=True)
with right:
    st.subheader("最近运行记录")
    if runs.empty:
        render_empty("还没有运行记录。执行数据更新、筛选或回测后会出现在这里。")
    else:
        st.dataframe(localize_table(runs), width="stretch", hide_index=True)

st.subheader("最近质量事件")
if events.empty:
    render_empty("暂无结构化质量事件。数据源失败、标的映射失败和质量检查事件会显示在这里。")
else:
    st.dataframe(localize_table(events), width="stretch", hide_index=True)
