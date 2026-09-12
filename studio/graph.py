"""Write and read Nosana / Daytona run logs as a Neo4j graph."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

DEFAULT_URI = "bolt://127.0.0.1:7687"


class GraphStore:
    """Persist agent turns and serve graph + analysis payloads for the studio."""

    def __init__(self) -> None:
        self.uri = (os.environ.get("NEO4J_URI") or DEFAULT_URI).strip()
        self.user = (
            os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER") or "neo4j"
        ).strip()
        self.password = (os.environ.get("NEO4J_PASSWORD") or "").strip()
        self.database = (os.environ.get("NEO4J_DATABASE") or "neo4j").strip()
        self.client_id = (
            os.environ.get("NEO4J_CLIENT_ID") or os.environ.get("CLIENT_ID") or ""
        ).strip()
        self.client_secret = (
            os.environ.get("NEO4J_CLIENT_SECRET") or os.environ.get("CLIENT_SECRET") or ""
        ).strip()
        self._driver = None
        self._memory: dict[str, Any] = {"nodes": {}, "edges": []}
        self.backend = "memory"
        self._connect()

    def _session(self):
        return self._driver.session(database=self.database)

    def _connect(self) -> None:
        try:
            driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            driver.verify_connectivity()
            self._driver = driver
            self.backend = "neo4j"
        except Exception:
            self._driver = None
            self.backend = "memory"

    def status(self) -> dict[str, str]:
        self.reconnect()
        instance_id = (
            os.environ.get("AURA_INSTANCEID") or os.environ.get("AURA_INSTANCE_ID") or ""
        ).strip()
        return {
            "backend": self.backend,
            "uri": self.uri,
            "database": self.database,
            "has_client_credentials": bool(self.client_id and self.client_secret),
            "aura_console_url": "https://console.neo4j.io",
            "aura_query_url": "https://workspace.neo4j.io/workspace/query",
            "aura_instance_url": (
                f"https://console.neo4j.io/?instance={instance_id}" if instance_id else "https://console.neo4j.io"
            ),
            "browser_url": (
                "https://browser.neo4j.io/?dbms="
                + self.uri.replace("://", "%3A%2F%2F")
                + f"&db={self.database}"
            ),
            "explore_cypher": (
                "MATCH (s:Session)-[:ASKED]->(p:Prompt)-[:PLANNED_ON]->(n:NosanaLog)"
                "-[:EXECUTED_IN]->(d:DaytonaLog) "
                "RETURN s, p, n, d ORDER BY p.created_at DESC LIMIT 25"
            ),
        }

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    def reconnect(self) -> None:
        """Retry Bolt if Neo4j came up after the app started."""
        if self._driver is not None:
            return
        self._connect()

    def record_turn(self, turn: dict[str, Any]) -> None:
        """Store one prompt → Nosana → Daytona cycle."""
        self.reconnect()
        if self._driver is None:
            self._record_memory(turn)
            return
        try:
            self._record_neo4j(turn)
        except Neo4jError:
            self._record_memory(turn)

    def _record_neo4j(self, turn: dict[str, Any]) -> None:
        query = """
        MERGE (s:Session {id: $session_id})
          ON CREATE SET s.created_at = $created_at
        CREATE (p:Prompt {
            id: $prompt_id, text: $prompt, created_at: $created_at
        })
        CREATE (n:NosanaLog {
            id: $nosana_id, provider: 'nosana', model: $model,
            reply: $nosana_reply, latency_ms: $nosana_ms,
            error: $nosana_error, created_at: $created_at
        })
        CREATE (d:DaytonaLog {
            id: $daytona_id, provider: 'daytona',
            code: $code, output: $daytona_output,
            latency_ms: $daytona_ms, error: $daytona_error,
            created_at: $created_at
        })
        MERGE (s)-[:ASKED]->(p)
        MERGE (p)-[:PLANNED_ON]->(n)
        MERGE (n)-[:EXECUTED_IN]->(d)
        MERGE (s)-[:RAN]->(d)
        """
        with self._session() as session:
            session.run(query, **self._params(turn))

    def _record_memory(self, turn: dict[str, Any]) -> None:
        p = self._params(turn)
        nodes = {
            p["session_id"]: {
                "id": p["session_id"],
                "label": "Session",
                "group": "session",
                "title": p["session_id"],
            },
            p["prompt_id"]: {
                "id": p["prompt_id"],
                "label": "Prompt",
                "group": "prompt",
                "title": p["prompt"],
            },
            p["nosana_id"]: {
                "id": p["nosana_id"],
                "label": "Nosana",
                "group": "nosana",
                "title": p["nosana_reply"] or p["nosana_error"],
            },
            p["daytona_id"]: {
                "id": p["daytona_id"],
                "label": "Daytona",
                "group": "daytona",
                "title": p["daytona_output"] or p["daytona_error"],
            },
        }
        self._memory["nodes"].update(nodes)
        self._memory["edges"].extend(
            [
                {"from": p["session_id"], "to": p["prompt_id"], "label": "ASKED"},
                {"from": p["prompt_id"], "to": p["nosana_id"], "label": "PLANNED_ON"},
                {"from": p["nosana_id"], "to": p["daytona_id"], "label": "EXECUTED_IN"},
                {"from": p["session_id"], "to": p["daytona_id"], "label": "RAN"},
            ]
        )

    def fetch_graph(self, limit: int = 80) -> dict[str, Any]:
        if self._driver is None:
            return {
                "nodes": list(self._memory["nodes"].values()),
                "edges": self._memory["edges"][-limit:],
                "backend": self.backend,
            }
        query = """
        MATCH (a)-[r]->(b)
        WHERE a:Session OR a:Prompt OR a:NosanaLog OR a:DaytonaLog
        RETURN a, r, b
        LIMIT $limit
        """
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        with self._session() as session:
            for record in session.run(query, limit=limit):
                for key in ("a", "b"):
                    node = record[key]
                    nid = node.get("id") or str(node.element_id)
                    labels = list(node.labels)
                    kind = labels[0] if labels else "Node"
                    nodes[nid] = {
                        "id": nid,
                        "label": self._short_label(kind, dict(node)),
                        "group": kind.lower().replace("log", ""),
                        "title": self._title(kind, dict(node)),
                    }
                rel = record["r"]
                start = record["a"].get("id") or str(record["a"].element_id)
                end = record["b"].get("id") or str(record["b"].element_id)
                edges.append({"from": start, "to": end, "label": rel.type})
        return {"nodes": list(nodes.values()), "edges": edges, "backend": self.backend}

    def fetch_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent prompt → Nosana → Daytona log rows."""
        self.reconnect()
        if self._driver is None:
            return self._runs_from_memory()
        query = """
        MATCH (s:Session)-[:ASKED]->(p:Prompt)-[:PLANNED_ON]->(n:NosanaLog)
              -[:EXECUTED_IN]->(d:DaytonaLog)
        RETURN s.id AS session_id, p.id AS prompt_id, p.text AS prompt,
               p.created_at AS created_at,
               n.reply AS nosana_reply, n.error AS nosana_error,
               n.latency_ms AS nosana_ms, n.model AS model,
               d.code AS code, d.output AS daytona_output,
               d.error AS daytona_error, d.latency_ms AS daytona_ms
        ORDER BY p.created_at DESC
        LIMIT $limit
        """
        with self._session() as session:
            rows = []
            for record in session.run(query, limit=limit):
                row = dict(record)
                created = row.get("created_at")
                if created is not None:
                    row["created_at"] = str(created)
                rows.append(row)
        return rows

    def analyze_runs(self, limit: int = 20) -> dict[str, Any]:
        """Compute timings and key messages from stored logs."""
        runs = self.fetch_runs(limit)
        nosana_times = [int(r.get("nosana_ms") or 0) for r in runs]
        daytona_times = [int(r.get("daytona_ms") or 0) for r in runs]
        nosana_fail = sum(1 for r in runs if r.get("nosana_error"))
        daytona_fail = sum(1 for r in runs if r.get("daytona_error"))
        latest = runs[0] if runs else None
        key_messages: list[str] = []
        if latest:
            if latest.get("prompt"):
                key_messages.append(f"Last prompt: {latest['prompt']}")
            if latest.get("nosana_error"):
                key_messages.append(f"Nosana error: {latest['nosana_error']}")
            elif latest.get("nosana_reply"):
                key_messages.append(f"Nosana code: {str(latest['nosana_reply'])[:240]}")
            if latest.get("daytona_error"):
                key_messages.append(f"Daytona error: {latest['daytona_error']}")
            elif latest.get("daytona_output"):
                key_messages.append(f"Daytona output: {str(latest['daytona_output']).strip()[:240]}")
        return {
            "run_count": len(runs),
            "nosana_failures": nosana_fail,
            "daytona_failures": daytona_fail,
            "avg_nosana_ms": int(sum(nosana_times) / len(nosana_times)) if nosana_times else 0,
            "avg_daytona_ms": int(sum(daytona_times) / len(daytona_times)) if daytona_times else 0,
            "max_nosana_ms": max(nosana_times) if nosana_times else 0,
            "max_daytona_ms": max(daytona_times) if daytona_times else 0,
            "total_pipeline_ms": int(sum(nosana_times) + sum(daytona_times)),
            "key_messages": key_messages,
            "runs": runs,
            "backend": self.backend,
        }

    def _runs_from_memory(self) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def _params(turn: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": turn["session_id"],
            "prompt_id": turn["prompt_id"],
            "nosana_id": turn["nosana_id"],
            "daytona_id": turn["daytona_id"],
            "created_at": turn.get("created_at")
            or datetime.now(timezone.utc).isoformat(),
            "prompt": turn["prompt"],
            "model": turn.get("model") or "gpt-oss:20b",
            "nosana_reply": turn.get("nosana_reply") or "",
            "nosana_error": turn.get("nosana_error") or "",
            "nosana_ms": int(turn.get("nosana_ms") or 0),
            "code": turn.get("code") or "",
            "daytona_output": turn.get("daytona_output") or "",
            "daytona_error": turn.get("daytona_error") or "",
            "daytona_ms": int(turn.get("daytona_ms") or 0),
        }

    @staticmethod
    def _short_label(kind: str, props: dict[str, Any]) -> str:
        if kind == "Prompt":
            text = (props.get("text") or "")[:28]
            return f"Prompt\n{text}"
        if kind == "NosanaLog":
            return "Nosana GPU"
        if kind == "DaytonaLog":
            return "Daytona"
        if kind == "Session":
            return "Session"
        return kind

    @staticmethod
    def _title(kind: str, props: dict[str, Any]) -> str:
        if kind == "Prompt":
            return props.get("text") or ""
        if kind == "NosanaLog":
            return props.get("reply") or props.get("error") or ""
        if kind == "DaytonaLog":
            return props.get("output") or props.get("error") or ""
        return str(props.get("id") or kind)
