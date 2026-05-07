from __future__ import annotations

import streamlit as st

from src.ui.state import recent_runs, recent_snapshots

st.title("Dashboard")
st.caption("研究用途，不构成投资建议。")
st.dataframe(recent_snapshots(), use_container_width=True)
st.dataframe(recent_runs(), use_container_width=True)
