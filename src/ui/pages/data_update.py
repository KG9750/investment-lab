from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import load_yaml
from src.ui.cli_bridge import build_update_args, run_cli

st.title("Data Update")
market = st.segmented_control("Market", ["CN", "HK", "US"], default="US")
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
source_mode = st.radio("Source", ["Custom symbols", "Universe"], horizontal=True)
universe = None
symbols = None
if source_mode == "Universe" and market_universes:
    universe = st.selectbox("Universe", market_universes)
elif source_mode == "Universe":
    st.info("No static universe is configured for this market yet. Use custom symbols.")
    symbols = st.text_input("Symbols", default_symbols[market], key=f"symbols_{market}")
else:
    symbols = st.text_input("Symbols", default_symbols[market], key=f"symbols_{market}")
start = st.text_input("Start", "2018-01-01")
adjust = st.selectbox(
    "Adjust",
    ["provider_default", "raw", "forward_adjusted", "backward_adjusted", "auto_adjusted"],
)
if st.button("Run update"):
    try:
        args = build_update_args(
            market=market,
            symbols=symbols,
            universe=universe,
            start=start,
            adjust=adjust,
        )
        result = run_cli(args)
        st.code(" ".join(result.command))
        st.write({"exit_code": result.returncode})
        st.json(result.json_summary or {})
        if result.stderr:
            st.code(result.stderr)
    except Exception as exc:
        st.error(str(exc))
