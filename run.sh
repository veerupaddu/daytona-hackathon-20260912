#!/usr/bin/env bash
# Start the studio UI in this terminal. Stops any previous :8000 process first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
UVICORN_BIN="$ROOT/.venv/bin/uvicorn"
ACTION="${1:-up}"

stop_studio() {
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids+=" $(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  pids+=" $(pgrep -f "uvicorn studio.app:app" 2>/dev/null || true)"
  pids="$(printf '%s\n' $pids | awk 'NF && !seen[$0]++')"
  if [[ -n "$pids" ]]; then
    echo "Stopping studio on :$PORT ($pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.4
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

case "$ACTION" in
  stop)
    stop_studio
    echo "Stopped studio."
    ;;
  up|restart|"")
    if [[ ! -x "$UVICORN_BIN" ]]; then
      echo "Missing $UVICORN_BIN"
      echo "Run one-time setup first:  ./onetime.sh" >&2
      exit 1
    fi
    stop_studio
    echo "Studio  http://$HOST:$PORT"
    echo "Ctrl+C to stop.  $0 stop  from another terminal also works."
    exec "$UVICORN_BIN" studio.app:app --reload --host "$HOST" --port "$PORT"
    ;;
  *)
    echo "Usage: $0 [up|stop]" >&2
    echo "One-time Neo4j / venv setup:  ./onetime.sh" >&2
    exit 2
    ;;
esac
