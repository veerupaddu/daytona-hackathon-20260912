#!/usr/bin/env bash
# Start local Neo4j from docker-compose.yml and wait until Bolt is ready.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

echo "Starting Neo4j (docker compose)..."
if docker compose up -d --wait; then
  :
else
  echo "compose --wait failed; starting without health wait..."
  docker compose up -d
  for _ in $(seq 1 40); do
    if docker compose exec -T neo4j cypher-shell -u neo4j -p hackathon 'RETURN 1' >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
fi

echo
echo "Neo4j is up"
echo "  Browser  http://127.0.0.1:7474"
echo "  Bolt     bolt://127.0.0.1:7687"
echo "  Auth     neo4j / hackathon"
echo
echo "Point .env at the local instance if you are not using Aura:"
echo "  NEO4J_URI=bolt://127.0.0.1:7687"
echo "  NEO4J_USERNAME=neo4j"
echo "  NEO4J_PASSWORD=hackathon"
echo "  NEO4J_DATABASE=neo4j"
echo
echo "Then:  python scripts/setup_neo4j.py"
echo "       uvicorn studio.app:app --reload --host 127.0.0.1 --port 8000"
echo "Stop:  docker compose down"
