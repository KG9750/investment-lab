from __future__ import annotations

import streamlit as st

from src.ui.cli_bridge import run_cli

st.title("Data Quality")
snapshot_id = st.text_input("Snapshot ID", "")
market = st.text_input("Market", "")
if st.button("Run quality check"):
    args = ["data-quality", "--output", "json"]
    if snapshot_id:
        args.extend(["--snapshot-id", snapshot_id])
    if market:
        args.extend(["--market", market])
    result = run_cli(args)
    st.code(" ".join(result.command))
    st.write({"exit_code": result.returncode})
    st.json(result.json_summary or {})
