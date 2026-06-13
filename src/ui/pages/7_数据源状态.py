from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ui.chrome import (
    inject_workbench_css,
    localize_table,
    page_header,
    render_empty,
    status_band,
)
from src.ui.cli_bridge import build_provider_health_args, stream_cli
from src.ui.state import recent_provider_health


def _try_json(line: str) -> dict | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


inject_workbench_css()
page_header(
    "数据源状态",
    "Provider Health",
    "检查免费数据源是否可用、是否限频、是否需要 fallback。",
)

cols = st.columns([1, 1, 1])
mode = cols[0].segmented_control("检查模式", ["quick", "full"], default="quick")
market_choice = cols[1].selectbox("市场", ["全部", "CN", "HK", "US"])
provider_choice = cols[2].selectbox(
    "数据源",
    ["全部", "akshare", "baostock", "efinance", "yfinance", "openbb"],
)
proxy_mode = st.selectbox(
    "网络模式",
    ["env", "direct"],
    help="env 使用当前代理环境；direct 临时直连。",
)
dry_run = st.checkbox("只检查，不写入台账", value=False)

if st.button("运行数据源健康检查"):
    args = build_provider_health_args(
        mode=mode,
        market=None if market_choice == "全部" else market_choice,
        provider=None if provider_choice == "全部" else provider_choice,
        proxy_mode=proxy_mode,
        dry_run=dry_run,
    )
    st.markdown(
        f'<div class="command-strip">{" ".join(["python", "-m", "src.cli", *args])}</div>',
        unsafe_allow_html=True,
    )
    log = st.empty()
    lines: list[str] = []
    final_summary = None
    for line in stream_cli(args):
        lines.append(line)
        log.code("".join(lines))
        payload = _try_json(line)
        if payload and "json_summary" in payload:
            final_summary = payload["json_summary"]
    status_band(final_summary)
    if final_summary:
        st.write({"退出码": 0 if final_summary.get("status") == "ok" else 1})
        matrix = pd.DataFrame(final_summary.get("matrix", []))
        attempts = pd.DataFrame(final_summary.get("attempts", []))
        if not matrix.empty:
            st.subheader("健康矩阵")
            st.dataframe(localize_table(matrix), width="stretch", hide_index=True)
        if not attempts.empty:
            st.subheader("检查明细")
            st.dataframe(localize_table(attempts), width="stretch", hide_index=True)

st.subheader("最近健康事件")
events = recent_provider_health()
if events.empty:
    render_empty("暂无数据源健康事件。")
else:
    st.dataframe(localize_table(events), width="stretch", hide_index=True)
