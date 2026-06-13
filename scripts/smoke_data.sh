#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROXY_MODE="${PROXY_MODE:-env}"

run_json_contract() {
  local name="$1"
  shift
  local tmp
  tmp="$(mktemp)"
  echo "==> ${name}"
  "$@" >"$tmp"
  local code=$?
  python - "$tmp" "$name" "$code" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
name = sys.argv[2]
code = int(sys.argv[3])
lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
payload = json.loads(lines[-1])
required = {
    "status",
    "task",
    "run_id",
    "config_hash",
    "row_count",
    "warning_count",
    "blocking_error_count",
    "started_at",
    "finished_at",
    "errors",
}
missing = sorted(required - set(payload))
if missing:
    raise SystemExit(f"{name}: missing JSON fields {missing}")
print(json.dumps({
    "name": name,
    "exit_code": code,
    "status": payload.get("status"),
    "task": payload.get("task"),
    "warning_count": payload.get("warning_count"),
    "blocking_error_count": payload.get("blocking_error_count"),
}, ensure_ascii=False))
PY
  local parse_code=$?
  cat "$tmp" > "data/logs/${name}.jsonl"
  rm -f "$tmp"
  return "$parse_code"
}

mkdir -p data/logs

failures=0

run_json_contract provider-health \
  uv run python -m src.cli provider-health \
    --mode quick \
    --proxy-mode "$PROXY_MODE" \
    --dry-run \
    --output json || failures=$((failures + 1))

run_json_contract cross-provider-check \
  uv run python -m src.cli cross-provider-check \
    --market US \
    --symbols SPY,QQQ \
    --proxy-mode "$PROXY_MODE" \
    --dry-run \
    --output json || failures=$((failures + 1))

if [[ "${RUN_REAL_UPDATE:-0}" == "1" ]]; then
  run_json_contract update-data \
    uv run python -m src.cli update-data \
      --market US \
      --symbols SPY \
      --start 2024-01-01 \
      --resume \
      --proxy-mode "$PROXY_MODE" \
      --output json || failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "smoke-data failed: ${failures} contract failure(s)"
  exit 1
fi

echo "smoke-data passed"
