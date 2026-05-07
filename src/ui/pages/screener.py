from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import list_yaml_files
from src.ui.cli_bridge import run_cli

st.title("Screener")
configs = list_yaml_files("configs/screens")
config = st.selectbox("Config", configs, format_func=lambda p: p.name)
if st.button("Run screen"):
    result = run_cli(["screen", "--config", str(config), "--output", "json"])
    st.code(" ".join(result.command))
    st.write({"exit_code": result.returncode})
    st.json(result.json_summary or {})
