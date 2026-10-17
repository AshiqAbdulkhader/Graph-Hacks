"""The only data-access layer. All relationship reasoning runs in FalkorDB."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from time import perf_counter
from typing import Any

from falkordb import FalkorDB

from app.config import settings


def _rows(result: Any) -> list[dict[str, Any]]:
    names = [item[1] for item in result.header]
    return [dict(zip(names, row, strict=True)) for row in result.result_set]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(*parts: str) -> str:
    return sha256("|".join(parts).encode()).hexdigest()[:16]


class GraphStore:
    def __init__(self, graph_name: str | None = None):
        self.db = FalkorDB(host=settings.host, port=settings.port, username=settings.username,
                           password=settings.password, ssl=settings.ssl)
        self.graph = self.db.select_graph(graph_name or settings.graph)

    def read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return _rows(self.graph.ro_query(query, params or {}))

    def write(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return _rows(self.graph.query(query, params or {}))

    def summary(self) -> dict[str, Any]:
        nodes = self.read("MATCH (n) RETURN count(n) AS count")[0]["count"]
        edges = self.read("MATCH ()-[r]->() RETURN count(r) AS count")[0]["count"]
        return {"nodes": nodes, "edges": edges, "graph": self.graph.name}

    def resolve_entity(self, text: str, limit: int = 8) -> dict[str, Any]:
        rows = self.read(
            "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($text) OR n.id = $text "
            "RETURN n.id AS id, n.name AS name, labels(n) AS labels LIMIT $limit",
            {"text": text, "limit": min(max(limit, 1), 20)},
        )
        return {"state": "found" if rows else "unknown_entity", "matches": rows}

    def decision_history(self, topic: str, as_of: str | None = None) -> dict[str, Any]:
        rows = self.read(
            "MATCH (d:Decision {topic_key: $topic}) "
            "OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(s:Source) "
            "RETURN d.id AS id, d.name AS statement, d.value AS value, "
            "d.valid_from AS valid_from, d.valid_to AS valid_to, d.status AS status, "
            "s.id AS source_id, s.quote AS quote ORDER BY valid_from",
            {"topic": topic},
        )
        current = next(
            (r for r in reversed(rows) if not as_of and r["status"] == "current"), None
        )
        if as_of:
            instant = datetime.fromisoformat(as_of)
            current = next(
                (r for r in reversed(rows)
                 if datetime.fromisoformat(r["valid_from"]) <= instant
                 and (not r["valid_to"] or instant < datetime.fromisoformat(r["valid_to"]))),
                None,
            )
        return {"topic": topic, "as_of": as_of, "current": current, "versions": rows}

    def _decision(self, decision_id: str) -> dict[str, Any] | None:
        rows = self.read(
            "MATCH (d:Decision {id: $id}) RETURN d.id AS id, d.topic_key AS topic, "
            "d.value AS value, d.status AS status, d.name AS statement",
            {"id": decision_id},
        )
        return rows[0] if rows else None

    def impact_of_change(self, decision_id: str, depth: int = 4, limit: int = 50) -> dict[str, Any]:
        decision = self._decision(decision_id)
        if not decision:
            return {"state": "unknown_entity", "decision_id": decision_id, "items": []}
        depth = min(max(depth, 1), 5)
        limit = min(max(limit, 1), 100)
        # The relationship length must be literal in FalkorDB; depth is validated above.
        query = (
            "MATCH (d:Decision {id: $id})-[:AFFECTS]->(root) "
            "MATCH path = (affected)-[:DEPENDS_ON*0.." + str(depth) + "]->(root) "
            "OPTIONAL MATCH (affected)-[:OWNED_BY]->(owner) "
            "RETURN affected.id AS id, affected.name AS name, labels(affected) AS labels, "
            "affected.due_at AS due_at, affected.version AS version, "
            "owner.id AS owner_id, owner.name AS owner, length(path) AS hops, "
            "[n IN nodes(path) | n.id] AS reverse_path "
            "ORDER BY hops, id LIMIT $limit"
        )
        rows = self.read(query, {"id": decision_id, "limit": limit})
        seen: set[str] = set()
        items = []
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            path = [decision_id, *reversed(row.pop("reverse_path"))]
            items.append({**row, "path": path, "evidence_state": "confirmed_dependency"})
        return {"state": "found" if items else "not_connected_in_graph", "decision_id": decision_id, "items": items}

    def find_stale_claims(self, decision_id: str) -> dict[str, Any]:
        if not self._decision(decision_id):
            return {"state": "unknown_entity", "items": []}
        rows = self.read(
            "MATCH (new:Decision {id: $id})-[:SUPERSEDES]->(old:Decision) "
            "MATCH (claim:Claim)-[:SUPPORTED_BY]->(old) "
            "MATCH (source:Source)-[:STATES]->(claim) "
            "OPTIONAL MATCH (source)-[:OWNED_BY]->(owner) "
            "RETURN claim.id AS id, claim.name AS statement, claim.status AS status, "
            "claim.quote AS quote, old.id AS old_decision_id, source.id AS source_id, "
            "source.name AS source, owner.id AS owner_id, owner.name AS owner "
            "ORDER BY source_id LIMIT 50",
            {"id": decision_id},
        )
        return {"state": "found" if rows else "none_recorded", "items": rows}

    def find_owner(self, entity_id: str) -> dict[str, Any]:
        rows = self.read(
            "MATCH (n {id: $id}) OPTIONAL MATCH (n)-[:OWNED_BY]->(owner) "
            "RETURN n.id AS id, n.name AS name, owner.id AS owner_id, owner.name AS owner",
            {"id": entity_id},
        )
        if not rows:
            return {"state": "unknown_entity", "entity_id": entity_id}
        return {"state": "found" if rows[0]["owner_id"] else "missing_owner", **rows[0]}

    def trace_why(self, from_id: str, to_id: str, depth: int = 5) -> dict[str, Any]:
        depth = min(max(depth, 1), 5)
        query = (
            "MATCH path = (a {id: $from_id})-[:AFFECTS|DEPENDS_ON*1.." + str(depth) + "]-(b {id: $to_id}) "
            "RETURN [n IN nodes(path) | n.id] AS path, length(path) AS hops "
            "ORDER BY hops LIMIT 1"
        )
        rows = self.read(query, {"from_id": from_id, "to_id": to_id})
        return {"state": "found" if rows else "not_connected_in_graph", "path": rows[0]["path"] if rows else []}

    def preview_decision(self, topic: str, value: str) -> dict[str, Any]:
        current = self.decision_history(topic)["current"]
        if not current:
            return {"state": "unknown_topic"}
        date.fromisoformat(value)
        old_date = date.fromisoformat(current["value"])
        delta = (date.fromisoformat(value) - old_date).days
        impact = self.impact_of_change(current["id"])
        return {
            "state": "simulation", "topic": topic, "old_value": current["value"], "new_value": value,
            "delta_days": delta, "affected": impact["items"], "mutated": False,
        }

    def commit_decision(self, topic: str, value: str, source_text: str, effective_at: str, event_id: str) -> dict[str, Any]:
        date.fromisoformat(value)
        datetime.fromisoformat(effective_at)
        if not source_text.strip() or len(source_text) > 4000:
            raise ValueError("Source text must be 1–4000 characters")
        if not event_id.strip() or len(event_id) > 128:
            raise ValueError("Event ID must be 1–128 characters")
        current = self.decision_history(topic)["current"]
        if not current:
            raise ValueError("Unknown decision topic")
        decision_id = f"decision:{topic}:{_key(event_id)}"
        existing = self._decision(decision_id)
        if existing:
            return {"state": "already_committed", "decision_id": decision_id, "impact": self.impact_of_change(decision_id), "drift": self.find_stale_claims(decision_id)}
        if current["value"] == value:
            raise ValueError("The proposed value matches the current decision")
        source_id = f"source:event:{_key(event_id)}"
        self.write(
            "MATCH (old:Decision {id: $old_id})-[:AFFECTS]->(root) "
            "SET old.status = 'superseded', old.valid_to = $effective_at "
            "CREATE (new:Decision {id: $new_id, topic_key: $topic, name: $statement, "
            "value: $value, valid_from: $effective_at, recorded_at: $recorded_at, status: 'current'}) "
            "CREATE (new)-[:SUPERSEDES]->(old) CREATE (new)-[:AFFECTS]->(root) "
            "CREATE (source:Source {id: $source_id, name: $source_name, kind: 'meeting', "
            "quote: $source_text, observed_at: $recorded_at}) "
            "CREATE (new)-[:SUPPORTED_BY]->(source) "
            "RETURN new.id AS id",
            {"old_id": current["id"], "new_id": decision_id, "topic": topic,
             "statement": f"{topic} changed to {value}", "value": value,
             "effective_at": effective_at, "recorded_at": _now(),
             "source_id": source_id, "source_name": f"Decision event {event_id}", "source_text": source_text},
        )
        impact = self.impact_of_change(decision_id)
        drift = self.find_stale_claims(decision_id)
        self._create_actions(decision_id, current["value"], value, impact["items"], drift["items"])
        return {"state": "committed", "decision_id": decision_id, "impact": impact, "drift": drift}

    def _create_actions(self, decision_id: str, old_value: str, new_value: str, impact: list[dict[str, Any]], drift: list[dict[str, Any]]) -> None:
        delta = (date.fromisoformat(new_value) - date.fromisoformat(old_value)).days
        for item in impact:
            if not item["due_at"]:
                continue
            target_date = (date.fromisoformat(item["due_at"]) + timedelta(days=delta)).isoformat()
            action_id = f"action:{_key(decision_id, item['id'], 'shift_date')}"
            status = "pending" if item["owner_id"] else "needs_owner"
            self.write(
                "MATCH (d:Decision {id: $decision_id}), (target {id: $target_id}) "
                "MERGE (a:ProposedAction {id: $action_id}) "
                "ON CREATE SET a.name = $name, a.type = 'shift_date', a.status = $status, "
                "a.target_value = $target_value, a.expected_version = $expected_version, "
                "a.created_at = $created_at, a.path_json = $path_json "
                "MERGE (a)-[:UPDATES]->(target) MERGE (a)-[:JUSTIFIED_BY]->(d)",
                {"decision_id": decision_id, "target_id": item["id"], "action_id": action_id,
                 "name": f"Move {item['name']} to {target_date}", "status": status,
                 "target_value": target_date, "expected_version": item["version"] or 1,
                 "created_at": _now(), "path_json": json.dumps(item["path"])},
            )
        for claim in drift:
            action_id = f"action:{_key(decision_id, claim['id'], 'review_claim')}"
            self.write(
                "MATCH (d:Decision {id: $decision_id}), (target:Claim {id: $target_id}) "
                "MERGE (a:ProposedAction {id: $action_id}) "
                "ON CREATE SET a.name = $name, a.type = 'review_claim', a.status = 'pending', "
                "a.target_value = $target_value, a.expected_version = 1, a.created_at = $created_at, "
                "a.path_json = $path_json "
                "MERGE (a)-[:UPDATES]->(target) MERGE (a)-[:JUSTIFIED_BY]->(d)",
                {"decision_id": decision_id, "target_id": claim["id"], "action_id": action_id,
                 "name": f"Review outdated claim in {claim['source']}", "target_value": new_value,
                 "created_at": _now(), "path_json": json.dumps([decision_id, claim["old_decision_id"], claim["id"]])},
            )

    def actions(self, decision_id: str | None = None) -> list[dict[str, Any]]:
        return self.read(
            "MATCH (a:ProposedAction)-[:JUSTIFIED_BY]->(d:Decision) "
            "MATCH (a)-[:UPDATES]->(target) "
            "WHERE $decision_id IS NULL OR d.id = $decision_id "
            "OPTIONAL MATCH (target)-[:OWNED_BY]->(owner) "
            "RETURN a.id AS id, a.name AS name, a.type AS type, a.status AS status, "
            "a.target_value AS target_value, a.expected_version AS expected_version, "
            "a.path_json AS path_json, d.id AS decision_id, target.id AS target_id, "
            "target.name AS target, target.due_at AS current_value, "
            "owner.id AS owner_id, owner.name AS owner ORDER BY a.name",
            {"decision_id": decision_id},
        )

    def review_action(self, action_id: str, approve: bool, reviewer: str, reason: str = "") -> dict[str, Any]:
        rows = [a for a in self.actions() if a["id"] == action_id]
        if not rows:
            raise ValueError("Unknown action")
        action = rows[0]
        if action["status"] in {"approved", "rejected"}:
            return {"state": "already_reviewed", "action": action}
        if action["status"] == "needs_owner" and approve:
            raise ValueError("An owner must be assigned before approving this action")
        if not reviewer.strip():
            raise ValueError("Reviewer is required")
        if action["type"] == "shift_date" and approve:
            result = self.write(
                "MATCH (a:ProposedAction {id: $action_id})-[:UPDATES]->(target) "
                "WHERE a.status = 'pending' AND target.version = a.expected_version "
                "SET target.due_at = a.target_value, target.version = target.version + 1, a.status = 'approved' "
                "RETURN target.id AS id",
                {"action_id": action_id},
            )
            if not result:
                raise ValueError("Target changed since action was drafted; regenerate the action")
        elif action["type"] == "review_claim" and approve:
            self.write(
                "MATCH (a:ProposedAction {id: $action_id})-[:UPDATES]->(claim:Claim) "
                "WHERE a.status = 'pending' "
                "SET claim.status = 'stale', a.status = 'approved' RETURN claim.id AS id",
                {"action_id": action_id},
            )
        else:
            self.write(
                "MATCH (a:ProposedAction {id: $action_id}) WHERE a.status IN ['pending', 'needs_owner'] "
                "SET a.status = 'rejected' RETURN a.id AS id",
                {"action_id": action_id},
            )
        review_id = f"review:{_key(action_id, 'approved' if approve else 'rejected')}"
        self.write(
            "MATCH (a:ProposedAction {id: $action_id}) "
            "MERGE (r:Review {id: $review_id}) "
            "ON CREATE SET r.name = $name, r.decision = $decision, r.reviewer = $reviewer, "
            "r.reason = $reason, r.reviewed_at = $reviewed_at "
            "MERGE (a)-[:REVIEWED_AS]->(r)",
            {"action_id": action_id, "review_id": review_id, "name": "Action review",
             "decision": "approved" if approve else "rejected", "reviewer": reviewer,
             "reason": reason, "reviewed_at": _now()},
        )
        return {"state": "approved" if approve else "rejected", "action_id": action_id}

    def tool_call(self, name: str, **kwargs: Any) -> dict[str, Any]:
        allowed = {
            "resolve_entity": self.resolve_entity,
            "decision_history": self.decision_history,
            "impact_of_change": self.impact_of_change,
            "find_stale_claims": self.find_stale_claims,
            "find_owner": self.find_owner,
            "trace_why": self.trace_why,
            "preview_decision": self.preview_decision,
        }
        if name not in allowed:
            raise ValueError("Unknown graph tool")
        start = perf_counter()
        result = allowed[name](**kwargs)
        return {"tool": name, "arguments": kwargs, "duration_ms": round((perf_counter() - start) * 1000, 2), "result": result}
