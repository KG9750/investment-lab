from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.ui.state import recent_runs, recent_snapshots

st.title("Dashboard")
st.caption("研究用途，不构成投资建议。")
st.dataframe(recent_snapshots(), width="stretch")
st.dataframe(recent_runs(), width="stretch")
