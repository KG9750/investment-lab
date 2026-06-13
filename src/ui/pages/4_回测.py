from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import list_yaml_files
from src.ui.chrome import inject_workbench_css, page_header, render_cli_result, render_empty
from src.ui.cli_bridge import run_cli

inject_workbench_css()
page_header("回测", "策略复盘")
configs = list_yaml_files("configs/backtests")
if not configs:
    render_empty("没有回测配置。请在 configs/backtests 下添加 YAML。")
else:
    config = st.selectbox("配置", configs, format_func=lambda p: p.name)
    st.caption("回测使用本地 Parquet 数据；策略信号默认延后一日执行。")
    if st.button("运行回测"):
        result = run_cli(["backtest", "--config", str(config), "--output", "json"])
        render_cli_result(result)
        summary = result.json_summary or {}
        path = summary.get("result_path") or summary.get("report_path")
        if path and str(path).endswith(".parquet") and Path(path).exists():
            frame = pd.read_parquet(path)
            if "date" in frame:
                frame["date"] = pd.to_datetime(frame["date"])
                frame = frame.sort_values("date")
            chart_columns = [
                column for column in ["equity", "drawdown", "gross_exposure"] if column in frame
            ]
            if chart_columns:
                st.subheader("曲线")
                st.line_chart(frame.set_index("date")[chart_columns])
            metric_cols = st.columns(4)
            metric_cols[0].metric("总收益", f"{summary.get('total_return', 0):.2%}")
            metric_cols[1].metric("最大回撤", f"{summary.get('max_drawdown', 0):.2%}")
            metric_cols[2].metric("夏普", f"{summary.get('sharpe', 0):.2f}")
            metric_cols[3].metric("总换手", f"{summary.get('turnover') or 0:.2f}")
            st.subheader("最近回测结果")
            st.dataframe(frame.tail(120), width="stretch", hide_index=True)
