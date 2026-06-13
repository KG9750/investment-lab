from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import load_yaml
from src.ui.chrome import inject_workbench_css, localize_table, page_header, status_band
from src.ui.cli_bridge import build_update_args, stream_cli


def _try_json(line: str) -> dict | None:
    try:
        import json

        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


inject_workbench_css()
page_header("数据更新", "数据源接入")

market = st.segmented_control("市场", ["CN", "HK", "US"], default="US")
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
