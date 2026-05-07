from __future__ import annotations

import streamlit as st

from src.config import DATA_DIR

st.title("Reports")
reports = sorted((DATA_DIR / "reports").glob("*"))
for report in reports:
    st.write(str(report))
