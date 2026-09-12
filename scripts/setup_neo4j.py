#!/usr/bin/env python3
"""One-time Neo4j schema for Nosana and Daytona logs.

Creates uniqueness constraints, lookup indexes, and a pipeline marker
node. Safe to re-run (IF NOT EXISTS).

Requires Bolt access from .env:

    NEO4J_URI
    NEO4J_USERNAME / NEO4J_PASSWORD   (instance user)
    NEO4J_DATABASE                    (optional, default neo4j)

Client credentials (CLIENT_ID / CLIENT_SECRET or NEO4J_CLIENT_*) are
optional metadata; Aura Bolt still uses the instance username and password.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT prompt_id IF NOT EXISTS FOR (p:Prompt) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT nosana_log_id IF NOT EXISTS FOR (n:NosanaLog) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT daytona_log_id IF NOT EXISTS FOR (d:DaytonaLog) REQUIRE d.id IS UNIQUE",
    "CREATE INDEX session_created_at IF NOT EXISTS FOR (s:Session) ON (s.created_at)",
    "CREATE INDEX prompt_created_at IF NOT EXISTS FOR (p:Prompt) ON (p.created_at)",
    "CREATE INDEX nosana_created_at IF NOT EXISTS FOR (n:NosanaLog) ON (n.created_at)",
    "CREATE INDEX daytona_created_at IF NOT EXISTS FOR (d:DaytonaLog) ON (d.created_at)",
    "CREATE INDEX nosana_provider IF NOT EXISTS FOR (n:NosanaLog) ON (n.provider)",
    "CREATE INDEX daytona_provider IF NOT EXISTS FOR (d:DaytonaLog) ON (d.provider)",
    "CREATE INDEX nosana_model IF NOT EXISTS FOR (n:NosanaLog) ON (n.model)",
]

PIPELINE_CYPHER = """
MERGE (p:LogPipeline {name: 'nosana-daytona'})
SET p.version = 1,
    p.node_labels = ['Session', 'Prompt', 'NosanaLog', 'DaytonaLog'],
    p.relationships = ['ASKED', 'PLANNED_ON', 'EXECUTED_IN', 'RAN'],
    p.client_name = $client_name,
    p.initialized_at = datetime()
RETURN p.name AS name
"""


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return default


def connect():
    """Open a driver from .env. Returns (driver, database)."""
    uri = _env("NEO4J_URI")
    user = _env("NEO4J_USERNAME", "NEO4J_USER", default="neo4j")
    password = _env("NEO4J_PASSWORD")
    database = _env("NEO4J_DATABASE", default="neo4j")
    if not uri:
        raise SystemExit("NEO4J_URI is missing from .env")
    if not password:
        raise SystemExit(
            "NEO4J_PASSWORD is missing from .env. "
            "Client id/secret are for the Aura API; Bolt needs the instance password."
        )
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver, database, uri


def apply_schema(driver, database: str) -> list[str]:
    """Create constraints, indexes, and the pipeline marker. Idempotent."""
    applied: list[str] = []
    client_name = _env("NEO4J_CLIENT_NAME", "CLIENT_NAME")
    with driver.session(database=database) as session:
        for statement in SCHEMA_STATEMENTS:
            session.run(statement)
            applied.append(statement.split(" IF NOT EXISTS")[0])
        session.run(PIPELINE_CYPHER, client_name=client_name)
        applied.append("MERGE LogPipeline {name: nosana-daytona}")
    return applied


def show_schema(driver, database: str) -> None:
    with driver.session(database=database) as session:
        constraints = list(session.run("SHOW CONSTRAINTS YIELD name RETURN name"))
        indexes = list(session.run("SHOW INDEXES YIELD name, type RETURN name, type"))
    print("Constraints:")
    for row in constraints:
        print(f"  - {row['name']}")
    print("Indexes:")
    for row in indexes:
        print(f"  - {row['name']} ({row['type']})")


def main() -> None:
    driver, database, uri = connect()
    print(f"Connected to {uri} (database={database})")
    try:
        applied = apply_schema(driver, database)
        print(f"Applied {len(applied)} schema steps:")
        for item in applied:
            print(f"  - {item}")
        show_schema(driver, database)
        print("One-time Neo4j setup complete.")
    finally:
        driver.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
