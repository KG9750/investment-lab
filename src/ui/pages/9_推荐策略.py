from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ui.chrome import inject_workbench_css, localize_table, page_header, render_cli_result
from src.ui.cli_bridge import build_data_status_args, run_cli
from src.ui.strategy_recommendations import recommend_strategies


def _config_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


inject_workbench_css()
page_header("推荐策略", "研究路线", "从不同角度生成候选研究策略；只用于研究，不构成投资建议。")

controls = st.columns([1, 1, 1, 1])
market = controls[0].segmented_control("市场", ["CN", "US", "HK"], default="CN")
objective = controls[1].selectbox(
    "研究目标",
    ["趋势确认", "资产轮动", "防守低波动", "稳健筛选", "数据优先", "探索备选"],
)
horizon = controls[2].selectbox("持有周期", ["短期", "中期", "长期"], index=1)
risk = controls[3].selectbox("风险偏好", ["低", "中", "高"], index=1)

status_universe = {
    "CN": "CN_REAL_CORE",
    "US": "US_ETF_ROTATION",
    "HK": "恒生科技",
}.get(market)

status_cols = st.columns([1, 3])
if status_cols[0].button("检查数据可用性"):
    result = run_cli(build_data_status_args(market=market, universe=status_universe))
    summary = result.json_summary or {}
    metric_cols = st.columns(5)
    metric_cols[0].metric("研究可用", summary.get("research_ready_symbol_count", 0))
    metric_cols[1].metric("过期", summary.get("stale_symbol_count", 0))
    metric_cols[2].metric("仅模拟", summary.get("synthetic_only_symbol_count", 0))
    metric_cols[3].metric("缺失", summary.get("missing_symbol_count", 0))
    metric_cols[4].metric("混合来源", summary.get("mixed_provider_symbol_count", 0))
    if summary.get("symbols"):
        st.dataframe(
            localize_table(pd.DataFrame(summary["symbols"])),
            width="stretch",
            hide_index=True,
        )
    elif result.returncode:
        render_cli_result(result)

recommendations = recommend_strategies(
    market=market,
    objective=objective,
    horizon=horizon,
    risk=risk,
)

table = pd.DataFrame(
    [
        {
            "分数": item["score"],
            "角度": item["angle"],
            "策略": item["title"],
            "筛选配置": item["screen_config"] or "待配置",
            "回测配置": item["backtest_config"] or "待配置",
            "下一步": item["next_step"],
        }
        for item in recommendations
    ]
)
st.subheader("推荐矩阵")
st.dataframe(table, width="stretch", hide_index=True)

for index, item in enumerate(recommendations, start=1):
    with st.expander(f"{index}. {item['title']}｜{item['angle']}", expanded=index == 1):
        st.write(item["rationale"])
        detail_rows = pd.DataFrame(
            [
                {"项目": "适用环境", "说明": item["best_when"]},
                {"项目": "主要风险", "说明": item["risk_note"]},
                {"项目": "数据要求", "说明": item["data_requirement"]},
                {"项目": "建议动作", "说明": item["next_step"]},
            ]
        )
        st.dataframe(detail_rows, width="stretch", hide_index=True)
        command_cols = st.columns(2)
        if item["screen_command"]:
            command_cols[0].markdown(
                f'<div class="command-strip">{item["screen_command"]}</div>',
                unsafe_allow_html=True,
            )
            if command_cols[0].button("运行筛选", key=f"screen_{item['key']}"):
                result = run_cli(
                    ["screen", "--config", item["screen_config"], "--output", "json"]
                )
                render_cli_result(result)
        else:
            command_cols[0].info("这个角度还没有筛选配置。")

        if item["backtest_command"]:
            command_cols[1].markdown(
                f'<div class="command-strip">{item["backtest_command"]}</div>',
                unsafe_allow_html=True,
            )
            if command_cols[1].button("运行回测", key=f"backtest_{item['key']}"):
                result = run_cli(
                    ["backtest", "--config", item["backtest_config"], "--output", "json"]
                )
                render_cli_result(result)
        else:
            command_cols[1].info("这个角度还没有回测配置。")

        if item["screen_config"] and not _config_exists(item["screen_config"]):
            st.warning(f"筛选配置不存在：{item['screen_config']}")
        if item["backtest_config"] and not _config_exists(item["backtest_config"]):
            st.warning(f"回测配置不存在：{item['backtest_config']}")
