from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ui.chrome import inject_workbench_css, page_header, render_cli_result
from src.ui.cli_bridge import run_cli

inject_workbench_css()
page_header("数据质量", "本地数据门禁")

left, right = st.columns([2, 1])
snapshot_id = left.text_input("快照 ID", "")
market = right.selectbox("市场", ["", "US", "CN", "HK"])
if st.button("运行质量检查"):
    args = ["data-quality", "--output", "json"]
    if snapshot_id:
        args.extend(["--snapshot-id", snapshot_id])
    if market:
        args.extend(["--market", market])
    result = run_cli(args)
    render_cli_result(result)
