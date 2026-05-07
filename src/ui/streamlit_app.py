from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ui.state import recent_runs, recent_snapshots

st.set_page_config(page_title="Investment Lab", layout="wide")
st.title("Investment Lab")
st.caption("研究用途，不构成投资建议。")

left, right = st.columns(2)
with left:
    st.subheader("Recent snapshots")
    st.dataframe(recent_snapshots(), width="stretch")
with right:
    st.subheader("Recent runs")
    st.dataframe(recent_runs(), width="stretch")
