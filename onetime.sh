#!/usr/bin/env bash
# One-time machine setup: venv, dependencies, local Neo4j, graph schema.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Creating .venv..."
  python3 -m venv "$ROOT/.venv"
  PYTHON="$ROOT/.venv/bin/python"
fi

echo "Installing Python dependencies..."
"$PYTHON" -m pip install -q -r "$ROOT/requirements.txt"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

echo "Starting Neo4j (docker compose)..."
if ! docker compose up -d --wait; then
  echo "compose --wait failed; starting without health wait..."
  docker compose up -d
  for _ in $(seq 1 40); do
    if docker compose exec -T neo4j cypher-shell -u neo4j -p hackathon 'RETURN 1' >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
fi

echo "Neo4j is up"
echo "  Browser  http://127.0.0.1:7474"
echo "  Bolt     bolt://127.0.0.1:7687"
echo "  Auth     neo4j / hackathon"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example — add API keys before running the UI."
fi

echo "Applying Neo4j schema..."
"$PYTHON" "$ROOT/scripts/setup_neo4j.py"

echo
echo "One-time setup finished."
echo "Start the UI with:  ./run.sh"
