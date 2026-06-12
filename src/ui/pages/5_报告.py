from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import DATA_DIR
from src.ui.chrome import inject_workbench_css, localize_table, page_header, render_empty
from src.ui.state import recent_cross_provider_checks, recent_provider_health

inject_workbench_css()
page_header("报告", "审计线索")

reports = sorted((DATA_DIR / "reports").glob("*"), reverse=True)
if not reports:
    render_empty(
        "暂无报告。先运行 backtest，再用 report 命令生成审计报告。",
        "python -m src.cli report --run-id <run-id> --output json",
    )
else:
    report = st.selectbox("报告", reports, format_func=lambda path: path.name)
    st.caption(str(report))
    if report.suffix == ".md":
        st.markdown(report.read_text(encoding="utf-8"))
    elif report.suffix == ".html":
        st.components.v1.html(report.read_text(encoding="utf-8"), height=720, scrolling=True)
    else:
        st.code(report.read_text(encoding="utf-8", errors="replace"))

st.subheader("最近数据源健康摘要")
health = recent_provider_health(20)
if health.empty:
    render_empty("暂无 provider health 事件。")
else:
    st.dataframe(localize_table(health), width="stretch", hide_index=True)

st.subheader("最近跨数据源差异")
cross = recent_cross_provider_checks(20)
if cross.empty:
    render_empty("暂无 cross-provider check 事件。")
else:
    st.caption("不判断真值，只提示不同数据源之间的差异。")
    st.dataframe(localize_table(cross), width="stretch", hide_index=True)
