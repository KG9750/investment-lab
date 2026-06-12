from __future__ import annotations

import sys
from pathlib import Path

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
