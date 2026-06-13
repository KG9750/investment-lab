#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${INVESTMENT_UI_PORT:-8501}"
while lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; do
  PORT="$((PORT + 1))"
done

mkdir -p data/logs
URL="http://localhost:${PORT}"

echo "Investment Lab UI"
echo "URL: ${URL}"
echo "Log: ${ROOT}/data/logs/streamlit-${PORT}.log"
echo

(sleep 2 && open "$URL" >/dev/null 2>&1 || true) &

if [[ -x ".venv/bin/streamlit" ]]; then
  exec .venv/bin/streamlit run src/ui/投资研究台.py \
    --server.port "$PORT" \
    --server.headless true \
    2>&1 | tee "data/logs/streamlit-${PORT}.log"
fi

exec uv run streamlit run src/ui/投资研究台.py \
  --server.port "$PORT" \
  --server.headless true \
  2>&1 | tee "data/logs/streamlit-${PORT}.log"
