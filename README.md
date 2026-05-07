# Investment Lab

本项目是本地可复现的个人投研、筛选与回测阶段一骨架。它参考只读设计文档：

`/Users/leo/Library/Mobile Documents/com~apple~CloudDocs/Personal/M4 Codex Workspace/Investment/INVESTMENT_AGENT_DESIGN.md`

定位是研究工具，不是实盘交易系统。所有候选股、回测和报告都必须追溯到本地数据、配置、`run_id`、`snapshot_id` 与 `config_hash`。

## Install

```bash
uv sync
```

如果当前系统 Python 过新导致部分重型依赖安装失败，可先使用 Python 3.11-3.13：

```bash
uv python install 3.13
uv sync --python 3.13
```

## CLI

规范入口是 `python -m src.cli`：

```bash
uv run python -m src.cli update-data --market US --symbols SPY,QQQ --start 2018-01-01 --resume --output json
uv run python -m src.cli data-quality --snapshot-id <snapshot-id> --output json
uv run python -m src.cli screen --config configs/screens/us_momentum.yaml --output json
uv run python -m src.cli backtest --config configs/backtests/etf_rotation_us.yaml --output json
uv run python -m src.cli report --run-id <run-id> --output json
uv run python -m src.cli compact --dataset prices --market US --output json
uv run python -m src.cli ui
```

所有非 UI 命令支持 `--output text` 和 `--output json`。失败时也会输出 JSON summary，并返回非零退出码。

## Data Layout

- DuckDB metadata: `data/investment.duckdb`
- Prices: `data/processed/prices/market=<MARKET>/date_month=<YYYY-MM>/part-*.parquet`
- Screens: `data/screens/`
- Backtests: `data/backtests/`
- Reports: `data/reports/`
- Quality reports: `data/metadata/`

`INVESTMENT_DB_PATH` 可覆盖默认 DuckDB 路径。

## UI

```bash
uv run streamlit run src/ui/streamlit_app.py
```

UI 只调用 CLI/service wrapper，不复制业务逻辑。页面会展示真实命令、退出码、`run_id`、`snapshot_id`、`config_hash` 和研究用途声明。

## Limitations

阶段一结果仅用于研究，不构成投资建议。A 股涨跌停、停牌、T+1、ST、退市、公司行动、历史成分股时点修正等限制会在报告中显式声明。
