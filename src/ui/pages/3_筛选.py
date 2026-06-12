from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config import list_yaml_files
from src.ui.chrome import inject_workbench_css, page_header, render_cli_result, render_empty
from src.ui.cli_bridge import run_cli

inject_workbench_css()
page_header("筛选", "候选过滤")
configs = list_yaml_files("configs/screens")
if not configs:
    render_empty("没有筛选配置。请在 configs/screens 下添加 YAML。")
else:
    config = st.selectbox("配置", configs, format_func=lambda p: p.name)
    st.caption("筛选前会执行本地价格质量门禁；blocking quality error 会阻止输出候选。")
    if st.button("运行筛选"):
        result = run_cli(["screen", "--config", str(config), "--output", "json"])
        render_cli_result(result)
