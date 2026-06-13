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
from src.ui.cli_bridge import build_cross_provider_args, stream_cli
from src.ui.state import recent_cross_provider_checks


def _try_json(line: str) -> dict | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


inject_workbench_css()
page_header("数据一致性", "Cross Provider Check", "不判断真值，只提示不同数据源之间的差异。")

market = st.segmented_control("市场", ["CN", "HK", "US"], default="US")
default_symbols = {
    "CN": "000001.SZ,600000.SH",
    "HK": "0700.HK,9988.HK",
    "US": "SPY,QQQ",
}
symbols = st.text_input("标的", default_symbols[market], key=f"cross_symbols_{market}")
cols = st.columns([1, 1, 1])
start = cols[0].text_input("起始日期", "2024-01-01")
end = cols[1].text_input("结束日期", "")
threshold = cols[2].number_input("close 差异阈值 %", value=0.5, min_value=0.0, step=0.1)
proxy_mode = st.selectbox(
    "网络模式",
    ["env", "direct"],
    help="env 使用当前代理环境；direct 临时直连。",
)
dry_run = st.checkbox("只检查，不写入台账", value=False)

if st.button("运行数据一致性检查"):
    args = build_cross_provider_args(
        market=market,
        symbols=symbols,
        start=start,
        end=end or None,
        close_threshold_pct=threshold,
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
        attempts = pd.DataFrame(final_summary.get("attempts", []))
        findings = pd.DataFrame(final_summary.get("findings", []))
        if not attempts.empty:
            st.subheader("数据源调用")
            st.dataframe(localize_table(attempts), width="stretch", hide_index=True)
        if not findings.empty:
            st.subheader("差异提示")
            category = st.multiselect(
                "类型过滤",
                sorted(findings["category"].dropna().unique().tolist()),
                default=sorted(findings["category"].dropna().unique().tolist()),
            )
            filtered = findings[findings["category"].isin(category)] if category else findings
            st.dataframe(localize_table(filtered), width="stretch", hide_index=True)
        else:
            render_empty("没有发现超过当前阈值的跨数据源差异。")

st.subheader("最近一致性事件")
events = recent_cross_provider_checks()
if events.empty:
    render_empty("暂无数据一致性检查事件。")
else:
    st.dataframe(localize_table(events), width="stretch", hide_index=True)
