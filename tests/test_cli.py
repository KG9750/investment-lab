import json
import subprocess
import sys


def test_cli_json_failure_contract() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "screen",
            "--config",
            "configs/screens/does_not_exist.yaml",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode != 0
    assert payload["status"] == "error"
    assert payload["task"] == "screen"
    assert payload["errors"]
