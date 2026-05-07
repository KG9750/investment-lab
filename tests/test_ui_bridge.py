from src.ui.cli_bridge import _last_json, build_update_args


def test_cli_bridge_reads_last_json_line() -> None:
    assert _last_json('log\n{"status":"ok"}\n') == {"status": "ok"}


def test_build_update_args_uses_market_symbols() -> None:
    args = build_update_args(
        market="CN",
        symbols="000001.SZ,600000.SH",
        universe=None,
        start="2018-01-01",
        adjust="provider_default",
    )
    assert "--market" in args
    assert args[args.index("--market") + 1] == "CN"
    assert args[args.index("--symbols") + 1] == "000001.SZ,600000.SH"
    assert "SPY,QQQ" not in args


def test_build_update_args_prefers_universe() -> None:
    args = build_update_args(
        market="US",
        symbols="SPY,QQQ",
        universe="US_ETF_ROTATION",
        start="2018-01-01",
        adjust="provider_default",
    )
    assert "--universe" in args
    assert "--symbols" not in args
