from src.ui.strategy_recommendations import recommend_strategies


def test_recommend_cn_trend_prefers_real_core_configs() -> None:
    rows = recommend_strategies(
        market="CN",
        objective="趋势确认",
        horizon="中期",
        risk="中",
    )

    assert rows[0]["key"] == "trend_ma"
    assert rows[0]["screen_config"] == "configs/screens/trend_cn_real_core.yaml"
    assert rows[0]["backtest_config"] == "configs/backtests/ma_cross_cn_real_core.yaml"
    assert rows[0]["screen_command"].endswith("--output json")


def test_recommend_us_rotation_exposes_backtest_command() -> None:
    rows = recommend_strategies(
        market="US",
        objective="资产轮动",
        horizon="中期",
        risk="中",
    )

    rotation = next(row for row in rows if row["key"] == "momentum_rotation")
    assert rotation["backtest_config"] == "configs/backtests/etf_rotation_us.yaml"
    assert "backtest" in rotation["backtest_command"]
