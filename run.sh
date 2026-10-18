#!/usr/bin/env bash
# Local one-command startup (no Docker): ./run.sh   |   ./run.sh --install  (pip install first)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
mkdir -p logs
[ -f .env ] && { set -a; . ./.env; set +a; }
export DEMO_MODE="${DEMO_MODE:-auto}"
if [ "${1:-}" = "--install" ]; then
  for t in task1-knowledge-brain task2-inbox-agent task3-meeting-to-sow; do python3 -m pip install -q -r "$t/requirements.txt"; done
fi
PIDS=()
cleanup() { echo; echo "Stopping services..."; kill "${PIDS[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
start() { # name dir port
  ( cd "$2" && PYTHONPATH="$ROOT/shared:$ROOT/$2" python3 -m uvicorn app.main:get_app --factory --host 0.0.0.0 --port "$3" ) \
    > "logs/$1.log" 2>&1 &
  PIDS+=($!)
}
export KNOWLEDGE_BRAIN_URL="${KNOWLEDGE_BRAIN_URL:-http://localhost:8001}"
start knowledge-brain task1-knowledge-brain 8001
start inbox-agent     task2-inbox-agent     8002
start meeting-to-sow  task3-meeting-to-sow  8003
( cd frontend/src && python3 -m http.server 8080 ) > logs/frontend.log 2>&1 &
PIDS+=($!)
for i in $(seq 1 40); do curl -fs localhost:8001/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fs localhost:8001/health >/dev/null || { echo "Knowledge Brain failed to start; see logs/knowledge-brain.log"; exit 1; }
if [ "$(curl -fs localhost:8001/health | python3 -c 'import sys,json;print(json.load(sys.stdin)["articles_active"])')" = "0" ]; then
  echo "Loading knowledge base (CRAWL_SOURCE=${CRAWL_SOURCE:-demo})..."
  curl -fs -X POST localhost:8001/api/v1/ingest -H 'content-type: application/json' -d '{}' >/dev/null || echo "Initial ingest failed; use the dashboard or POST /api/v1/ingest"
fi
echo "Dashboard:        http://localhost:8080"
echo "Knowledge Brain:  http://localhost:8001/docs"
echo "Inbox Agent:      http://localhost:8002/docs"
echo "Meeting to SOW:   http://localhost:8003/docs"
echo "AI mode: ${DEMO_MODE} (auto = live only if ANTHROPIC_API_KEY and ANTHROPIC_MODEL are set). Ctrl+C to stop."
wait
