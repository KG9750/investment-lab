from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.config import PROJECT_ROOT


@dataclass
class CliResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    json_summary: dict | None


def run_cli(args: Iterable[str], timeout: int | None = None) -> CliResult:
    command = [sys.executable, "-m", "src.cli", *args]
    proc = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CliResult(command, proc.returncode, proc.stdout, proc.stderr, _last_json(proc.stdout))


def stream_cli(args: Iterable[str]):
    command = [sys.executable, "-m", "src.cli", *args]
    proc = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line)
        yield line
    proc.wait()
    summary = _last_json("".join(lines))
    yield json.dumps(
        {"command": command, "returncode": proc.returncode, "json_summary": summary},
        ensure_ascii=False,
    )


def _last_json(text: str) -> dict | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


def open_report(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_update_args(
    *,
    market: str,
    start: str,
    adjust: str,
    symbols: str | None = None,
    universe: str | None = None,
    resume: bool = True,
) -> list[str]:
    args = [
        "update-data",
        "--market",
        market,
        "--start",
        start,
        "--adjust",
        adjust,
    ]
    if universe:
        args.extend(["--universe", universe])
    elif symbols:
        args.extend(["--symbols", symbols])
    else:
        raise ValueError("Either symbols or universe is required")
    if resume:
        args.append("--resume")
    args.extend(["--output", "json"])
    return args
