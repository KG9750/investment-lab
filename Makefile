.PHONY: test lint ui start-ui update-data screen backtest report compact provider-health cross-provider-check smoke-data

test:
	uv run pytest

lint:
	uv run ruff check .

ui:
	uv run streamlit run src/ui/投资研究台.py

start-ui:
	./scripts/start_ui.sh

update-data:
	uv run python -m src.cli update-data --market US --symbols SPY,QQQ --start 2018-01-01 --resume --output json

screen:
	uv run python -m src.cli screen --config configs/screens/us_momentum.yaml --output json

backtest:
	uv run python -m src.cli backtest --config configs/backtests/etf_rotation_us.yaml --output json

report:
	uv run python -m src.cli report --run-id "$(RUN_ID)" --output json

compact:
	uv run python -m src.cli compact --dataset prices --market US --output json

provider-health:
	uv run python -m src.cli provider-health --mode quick --dry-run --output json

cross-provider-check:
	uv run python -m src.cli cross-provider-check --market US --symbols SPY,QQQ --dry-run --output json

smoke-data:
	./scripts/smoke_data.sh
