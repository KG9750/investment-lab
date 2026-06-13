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

`vectorbt` 当前不是阶段一默认运行依赖。如需后续实验 vectorbt 适配器，可安装可选依赖：

```bash
uv sync --extra vectorbt
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
uv run python -m src.cli provider-health --mode quick --dry-run --output json
uv run python -m src.cli provider-health --mode quick --proxy-mode direct --dry-run --output json
uv run python -m src.cli cross-provider-check --market US --symbols SPY,QQQ --dry-run --output json
uv run python -m src.cli ui
```

所有非 UI 命令支持 `--output text` 和 `--output json`。失败时也会输出 JSON summary，并返回非零退出码。

`provider-health` 用来检查数据源可用性、耗时、错误类型和可重试状态；`cross-provider-check` 用来比较不同数据源之间的行数、缺失日期、OHLC 合法性和 close 差异。后者不判断哪个数据源是真值，只提示差异。

`--proxy-mode env|direct` 可临时覆盖数据源网络模式：

- `env`：使用当前 shell / 系统代理环境变量，这是默认值。
- `direct`：本次请求临时清空代理环境变量，用于排查代理导致的 `proxy_error`。

## Data Layout

- DuckDB metadata: `data/investment.duckdb`
- Prices: `data/processed/prices/market=<MARKET>/date_month=<YYYY-MM>/part-*.parquet`
- Screens: `data/screens/`
- Backtests: `data/backtests/`
- Reports: `data/reports/`
- Quality reports: `data/metadata/`

`INVESTMENT_DATA_DIR` 可覆盖默认数据目录，`INVESTMENT_DB_PATH` 可覆盖默认 DuckDB 路径。

## Data Sources

默认不启用 Tushare，因为它依赖 token 和积分。当前阶段使用免费/公开数据源：

- CN price: `akshare -> baostock -> efinance`
- HK price: `akshare -> yfinance -> efinance`
- US price: `yfinance -> efinance`

免费数据源可能限频、延迟或字段变化；每次抓取会记录 provider attempt 和质量事件，供报告追溯。
本机网络或代理异常时，健康检查会返回 `proxy_error`、`timeout`、`empty_response` 等结构化错误。

## UI

```bash
uv run streamlit run src/ui/投资研究台.py
```

本机日常使用建议走启动器，它会自动选择可用端口并打开浏览器：

```bash
./scripts/start_ui.sh
```

UI 只调用 CLI/service wrapper，不复制业务逻辑。页面会展示真实命令、退出码、`run_id`、`snapshot_id`、`config_hash` 和研究用途声明。

主要页面：

- 总览：运行台账、数据快照、最近质量/健康/一致性事件。
- 数据更新：展示每个标的的最终 provider、fallback 链路和失败原因。
- 数据源状态：运行 `provider-health`，展示 provider × market 健康矩阵。
- 数据一致性：运行 `cross-provider-check`，展示跨数据源差异。
- 筛选、回测、报告、数据质量：继续通过 CLI 调用业务能力并展示结果。

## Smoke Checks

普通测试不访问真实网络：

```bash
uv run ruff check .
uv run pytest
```

需要检查本机数据源连通性和 JSON 契约时：

```bash
make smoke-data
PROXY_MODE=direct make smoke-data
```

默认 smoke 只跑 dry-run 的 provider health 和 cross-provider check。若要尝试真实写入行情数据：

```bash
RUN_REAL_UPDATE=1 make smoke-data
```

## Limitations

阶段一结果仅用于研究，不构成投资建议。A 股涨跌停、停牌、T+1、ST、退市、公司行动、历史成分股时点修正等限制会在报告中显式声明。
