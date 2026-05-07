from __future__ import annotations

import streamlit as st

from src.config import list_yaml_files
from src.ui.cli_bridge import run_cli

st.title("Backtest")
configs = list_yaml_files("configs/backtests")
config = st.selectbox("Config", configs, format_func=lambda p: p.name)
if st.button("Run backtest"):
    result = run_cli(["backtest", "--config", str(config), "--output", "json"])
    st.code(" ".join(result.command))
    st.write({"exit_code": result.returncode})
    st.json(result.json_summary or {})
