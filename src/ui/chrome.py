from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from src.ui.cli_bridge import CliResult

COLUMN_LABELS = {
    "snapshot_id": "快照 ID",
    "market": "市场",
    "dataset": "数据集",
    "provider": "数据源",
    "snapshot_created_at": "快照创建时间",
    "min_date": "起始日期",
    "max_date": "结束日期",
    "row_count": "行数",
    "config_hash": "配置哈希",
    "run_id": "运行 ID",
    "task": "任务",
    "config_path": "配置路径",
    "data_range_start": "数据起始",
    "data_range_end": "数据结束",
    "provider_summary": "数据源摘要",
    "created_at": "创建时间",
    "finished_at": "完成时间",
    "status": "状态",
    "warning_count": "警告数",
    "blocking_error_count": "阻断错误数",
    "report_path": "报告路径",
    "errors": "错误",
    "event_type": "事件类型",
    "severity": "级别",
    "symbol": "标的",
    "message": "消息",
    "retryable": "可重试",
    "details": "详情",
    "error_type": "错误类型",
    "elapsed_ms": "耗时 ms",
    "fallback_reason": "Fallback 原因",
    "ok": "成功",
    "avg_elapsed_ms": "平均耗时 ms",
    "ok_count": "成功数",
    "failed_count": "失败数",
    "last_message": "最近消息",
    "category": "类型",
    "diff_pct": "差异百分比",
}


def inject_workbench_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --paper: #f8ecd8;
          --paper-2: #ead9bc;
          --paper-3: #fff7ea;
          --ink: #3a261b;
          --ink-2: #623625;
          --muted: #846b56;
          --rule: #6f442d;
          --sakura: #f56f8f;
          --momo: #f7a6b8;
          --sky: #5fb3d9;
          --matcha: #75a86b;
          --gold: #e7b64a;
          --violet: #8d75bd;
          --green: #2d745f;
          --red: #b73d33;
          --amber: #a86e15;
        }
        .stApp {
          background:
            radial-gradient(circle at 18px 18px, rgba(181,61,51,.08) 0 2px, transparent 2px),
            linear-gradient(90deg, rgba(58,38,27,.07) 1px, transparent 1px) 0 0/38px 38px,
            linear-gradient(180deg, var(--paper), var(--paper-3) 46%);
          color: var(--ink);
        }
        .block-container {
          padding-top: 1.25rem;
          padding-bottom: 4rem;
          max-width: 1180px;
        }
        h1, h2, h3 {
          letter-spacing: 0;
          color: var(--ink);
        }
        h1 {
          font-family: "Avenir Next Condensed", "Helvetica Neue", sans-serif;
          font-weight: 900;
          font-size: clamp(3rem, 5vw, 5.6rem);
          line-height: .88;
          color: var(--ink-2);
        }
        h2, h3 {
          font-family: "Avenir Next", "Helvetica Neue", sans-serif;
          font-weight: 800;
        }
        section[data-testid="stSidebar"] {
          background:
            linear-gradient(180deg, rgba(58,38,27,.94), rgba(83,49,34,.96)),
            var(--ink);
        }
        div[data-testid="stSidebar"] {
          background:
            linear-gradient(180deg, rgba(58,38,27,.94), rgba(83,49,34,.96)),
            var(--ink);
          border-right: 4px solid var(--sakura);
        }
        div[data-testid="stSidebar"] a,
        div[data-testid="stSidebar"] span,
        div[data-testid="stSidebar"] p {
          color: #fff1df !important;
        }
        div[data-testid="stAppDeployButton"],
        div[data-testid="stMainMenu"],
        button[data-testid="stMainMenuButton"],
        div[data-testid="stElementToolbarButton"] {
          display: none !important;
        }
        div[data-testid="stMetric"] {
          position: relative;
          background: rgba(255,247,234,.84);
          border: 2px solid var(--rule);
          border-radius: 0;
          box-shadow: 5px 5px 0 rgba(58,38,27,.18);
          padding: .9rem .9rem .8rem;
          overflow: hidden;
        }
        div[data-testid="stMetric"]::before {
          content: "";
          position: absolute;
          inset: 0 0 auto 0;
          height: 9px;
          background: linear-gradient(
            90deg,
            var(--sakura) 0 16.6%,
            var(--sky) 16.6% 33.2%,
            var(--matcha) 33.2% 49.8%,
            var(--gold) 49.8% 66.4%,
            var(--violet) 66.4% 83%,
            var(--red) 83% 100%
          );
        }
        div[data-testid="stMetricLabel"] p {
          color: var(--muted);
          font-size: .78rem;
        }
        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] *,
        div[role="radiogroup"] label,
        div[role="radiogroup"] p {
          color: var(--ink) !important;
          font-weight: 650;
        }
        input,
        textarea,
        [data-testid="stTextInputRootElement"],
        [data-baseweb="base-input"],
        div[data-baseweb="select"] > div {
          background: var(--paper-3) !important;
          color: var(--ink) !important;
          border-color: rgba(111,68,45,.46) !important;
          border-radius: 0 !important;
        }
        div[data-baseweb="button-group"] button {
          background: var(--paper-3) !important;
          color: var(--ink) !important;
          border-color: rgba(111,68,45,.42) !important;
          border-radius: 0 !important;
        }
        div[data-baseweb="button-group"] button[aria-pressed="true"] {
          color: #fff6e8 !important;
          background: var(--red) !important;
        }
        .workbench-head {
          position: relative;
          border: 3px solid var(--rule);
          border-left-width: 16px;
          border-radius: 0;
          padding: 1.1rem 1.25rem 1.25rem;
          margin-bottom: 1.5rem;
          background:
            linear-gradient(90deg, rgba(255,247,234,.92), rgba(255,247,234,.68)),
            var(--paper-3);
          box-shadow: 8px 8px 0 rgba(58,38,27,.16);
          overflow: hidden;
        }
        .workbench-head::before {
          content: "";
          position: absolute;
          inset: 0 0 auto 0;
          height: 14px;
          background: linear-gradient(
            90deg,
            var(--sakura) 0 16.6%,
            var(--sky) 16.6% 33.2%,
            var(--matcha) 33.2% 49.8%,
            var(--gold) 49.8% 66.4%,
            var(--violet) 66.4% 83%,
            var(--red) 83% 100%
          );
        }
        .workbench-head::after {
          content: "";
          position: absolute;
          right: 1.2rem;
          top: 1.45rem;
          width: 88px;
          height: 88px;
          border: 5px solid rgba(183,61,51,.85);
          border-radius: 50%;
          transform: rotate(-10deg);
          opacity: .72;
        }
        .workbench-title-row {
          position: relative;
          z-index: 1;
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 1rem;
          align-items: start;
          padding-top: .45rem;
        }
        .workbench-stamp {
          color: var(--red);
          border: 3px solid var(--red);
          padding: .32rem .45rem;
          font-size: .74rem;
          font-weight: 900;
          line-height: 1;
          transform: rotate(-8deg);
          text-transform: uppercase;
          letter-spacing: .08em;
        }
        .workbench-kicker {
          color: var(--red);
          font-size: .78rem;
          letter-spacing: .12em;
          text-transform: uppercase;
          margin-bottom: .55rem;
          font-weight: 900;
        }
        .research-declare {
          color: var(--muted);
          font-size: .9rem;
          margin-top: .55rem;
          font-weight: 650;
        }
        .status-band {
          display: flex;
          gap: .75rem;
          align-items: center;
          justify-content: space-between;
          border: 2px solid var(--rule);
          border-top: 10px solid var(--green);
          border-radius: 0;
          padding: .9rem 1rem;
          background: rgba(255,247,234,.86);
          margin: .7rem 0 1rem;
          box-shadow: 5px 5px 0 rgba(58,38,27,.13);
        }
        .status-band.error { border-top-color: var(--red); }
        .status-band.warn { border-top-color: var(--amber); }
        .status-label {
          font-size: .72rem;
          color: var(--red);
          text-transform: uppercase;
          letter-spacing: .08em;
          font-weight: 900;
        }
        .status-value {
          font-weight: 800;
          color: var(--ink);
        }
        .empty-note {
          border: 2px dashed rgba(111,68,45,.72);
          border-radius: 0;
          padding: 1rem;
          color: var(--muted);
          background: rgba(255,247,234,.7);
        }
        .command-strip {
          border: 2px solid var(--rule);
          border-radius: 0;
          padding: .78rem .85rem;
          background: var(--ink);
          color: #fff1df;
          font-size: .82rem;
          overflow-wrap: anywhere;
          box-shadow: 4px 4px 0 rgba(183,61,51,.22);
        }
        .stButton > button {
          border-radius: 0;
          border: 2px solid var(--rule);
          background: var(--red);
          color: #fff6e8;
          font-weight: 850;
          box-shadow: 4px 4px 0 rgba(58,38,27,.22);
        }
        .stButton > button:hover {
          border-color: var(--rule);
          background: var(--ink-2);
          color: #fff6e8;
          transform: translate(1px, 1px);
          box-shadow: 2px 2px 0 rgba(58,38,27,.24);
        }
        div[data-testid="stDataFrame"] {
          border: 2px solid var(--rule);
          box-shadow: 5px 5px 0 rgba(58,38,27,.12);
        }
        @media (max-width: 720px) {
          .workbench-title-row {
            grid-template-columns: 1fr;
          }
          .workbench-stamp {
            width: max-content;
          }
          .status-band {
            display: grid;
            grid-template-columns: 1fr;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, kicker: str, caption: str | None = None) -> None:
    st.markdown(
        f"""
        <div class="workbench-head">
          <div class="workbench-title-row">
            <div>
              <div class="workbench-kicker">{kicker}</div>
              <h1>{title}</h1>
              <div class="research-declare">{caption or "研究用途，不构成投资建议。"}</div>
            </div>
            <div class="workbench-stamp">本地<br>研究</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_band(summary: Mapping[str, Any] | None) -> None:
    if not summary:
        st.markdown(
            '<div class="empty-note">暂无运行结果。先执行左侧页面中的本地 CLI 任务。</div>',
            unsafe_allow_html=True,
        )
        return
    status = str(summary.get("status", "unknown"))
    cls = "error" if status == "error" else "warn" if summary.get("warning_count") else ""
    run_id = summary.get("run_id")
    snapshot_id = summary.get("snapshot_id")
    config_hash = summary.get("config_hash")
    items = "\n".join(
        [
            _status_item("状态", status),
            _status_item("运行 ID", run_id),
            _status_item("快照 ID", snapshot_id),
            _status_item("配置哈希", config_hash),
        ]
    )
    st.markdown(
        f"""
        <div class="status-band {cls}">
          {items}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cli_result(result: CliResult) -> None:
    st.markdown(
        f'<div class="command-strip">{" ".join(result.command)}</div>',
        unsafe_allow_html=True,
    )
    status_band(result.json_summary)
    st.write({"退出码": result.returncode})
    if result.json_summary:
        st.json(result.json_summary)
    if result.stderr:
        st.code(result.stderr)


def render_empty(message: str, command: str | None = None) -> None:
    st.markdown(f'<div class="empty-note">{message}</div>', unsafe_allow_html=True)
    if command:
        st.markdown(f'<div class="command-strip">{command}</div>', unsafe_allow_html=True)


def localize_table(df):
    return df.rename(columns={key: value for key, value in COLUMN_LABELS.items() if key in df})


def _status_item(label: str, value: object) -> str:
    return (
        f'<div><div class="status-label">{label}</div>'
        f'<div class="status-value">{value}</div></div>'
    )
