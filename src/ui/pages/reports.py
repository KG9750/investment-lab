from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import DATA_DIR

st.title("Reports")
reports = sorted((DATA_DIR / "reports").glob("*"))
for report in reports:
    st.write(str(report))
