from __future__ import annotations

import streamlit as st

from src.ui.cli_bridge import run_cli

st.title("Data Update")
market = st.segmented_control("Market", ["CN", "HK", "US"], default="US")
symbols = st.text_input("Symbols", "SPY,QQQ")
start = st.text_input("Start", "2018-01-01")
adjust = st.selectbox(
    "Adjust",
    ["provider_default", "raw", "forward_adjusted", "backward_adjusted", "auto_adjusted"],
)
if st.button("Run update"):
    args = [
        "update-data",
        "--market",
        market,
        "--symbols",
        symbols,
        "--start",
        start,
        "--adjust",
        adjust,
        "--resume",
        "--output",
        "json",
    ]
    result = run_cli(args)
    st.code(" ".join(result.command))
    st.write({"exit_code": result.returncode})
    st.json(result.json_summary or {})
    if result.stderr:
        st.code(result.stderr)
