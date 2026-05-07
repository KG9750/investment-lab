.PHONY: test lint ui update-data screen backtest report compact

test:
	uv run pytest

lint:
	uv run ruff check .

ui:
	uv run streamlit run src/ui/streamlit_app.py

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
