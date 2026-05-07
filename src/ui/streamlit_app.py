from __future__ import annotations

import streamlit as st

from src.ui.state import recent_runs, recent_snapshots

st.set_page_config(page_title="Investment Lab", layout="wide")
st.title("Investment Lab")
st.caption("研究用途，不构成投资建议。")

left, right = st.columns(2)
with left:
    st.subheader("Recent snapshots")
    st.dataframe(recent_snapshots(), use_container_width=True)
with right:
    st.subheader("Recent runs")
    st.dataframe(recent_runs(), use_container_width=True)
