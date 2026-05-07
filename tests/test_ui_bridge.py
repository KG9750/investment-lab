from src.ui.cli_bridge import _last_json


def test_cli_bridge_reads_last_json_line() -> None:
    assert _last_json('log\n{"status":"ok"}\n') == {"status": "ok"}
