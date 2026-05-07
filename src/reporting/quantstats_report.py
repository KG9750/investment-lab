from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import DATA_DIR


def generate_quantstats_html(returns: pd.Series, run_id: str) -> Path:
    path = DATA_DIR / "reports" / f"{run_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import quantstats as qs

        qs.reports.html(returns, output=str(path), title=f"Investment Lab {run_id}")
    except Exception:
        equity = (1 + returns.fillna(0)).cumprod()
        html = f"""<html><body><h1>Investment Lab {run_id}</h1>
<p>QuantStats unavailable; fallback report generated.</p>
<p>Total return: {equity.iloc[-1] - 1 if not equity.empty else 0:.2%}</p>
</body></html>"""
        path.write_text(html, encoding="utf-8")
    return path
