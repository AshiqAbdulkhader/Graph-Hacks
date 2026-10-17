"""Deterministic, wholly fictional company fixture."""

from __future__ import annotations

from falkordb import FalkorDB

from app.config import settings


NODES = [
    ("Decision", "decision:atlas-tuesday", "Atlas launches Tuesday", {"topic_key": "atlas-launch", "value": "2026-10-20", "valid_from": "2026-10-15T00:00:00+05:30", "recorded_at": "2026-10-15T09:00:00+05:30", "status": "current"}),
    ("Decision", "decision:beacon-november", "Beacon launches in November", {"topic_key": "beacon-launch", "value": "2026-11-12", "valid_from": "2026-10-15T00:00:00+05:30", "recorded_at": "2026-10-15T09:00:00+05:30", "status": "current"}),
    ("Source", "source:atlas-kickoff", "Atlas kickoff notes", {"kind": "meeting", "quote": "Atlas launches Tuesday, October 20."}),
    ("Source", "source:atlas-brief", "Atlas launch brief", {"kind": "document", "quote": "Public launch is Tuesday, October 20."}),
    ("Source", "source:partner-plan", "Partner announcement plan", {"kind": "document", "quote": "The partner announcement follows the public launch."}),
    ("Claim", "claim:atlas-tuesday", "Atlas launches Tuesday", {"status": "current", "quote": "Public launch is Tuesday, October 20."}),
    ("Project", "project:atlas", "Atlas", {"status": "active"}),
    ("Project", "project:beacon", "Beacon", {"status": "active"}),
    ("Milestone", "milestone:atlas-launch", "Atlas public launch", {"due_at": "2026-10-20", "version": 1, "status": "planned"}),
    ("Milestone", "milestone:localization", "Atlas localization complete", {"due_at": "2026-10-19", "version": 1, "status": "in_progress"}),
    ("Milestone", "milestone:beacon-launch", "Beacon public launch", {"due_at": "2026-11-12", "version": 1, "status": "planned"}),
    ("Deliverable", "deliverable:launch-brief", "Atlas launch brief", {"due_at": "2026-10-20", "version": 1, "status": "planned"}),
    ("Deliverable", "deliverable:partner-announcement", "Partner announcement", {"due_at": "2026-10-20", "version": 1, "status": "planned"}),
    ("Deliverable", "deliverable:social-kit", "Social media kit", {"due_at": "2026-10-20", "version": 1, "status": "planned"}),
    ("Deliverable", "deliverable:beacon-brief", "Beacon launch brief", {"due_at": "2026-11-12", "version": 1, "status": "planned"}),
    ("Commitment", "commitment:partner-preview", "Partner preview commitment", {"due_at": "2026-10-20", "version": 1, "status": "promised"}),
    ("Commitment", "commitment:customer-webinar", "Customer webinar commitment", {"due_at": "2026-10-21", "version": 1, "status": "promised"}),
    ("Team", "team:product", "Product", {}),
    ("Team", "team:marketing", "Marketing", {}),
    ("Team", "team:partnerships", "Partnerships", {}),
    ("Person", "person:maya", "Maya", {"role": "Product lead"}),
    ("Person", "person:priya", "Priya", {"role": "Marketing lead"}),
    ("Person", "person:leo", "Leo", {"role": "Partner manager"}),
]

EDGES = [
    ("decision:atlas-tuesday", "SUPPORTED_BY", "source:atlas-kickoff"),
    ("decision:atlas-tuesday", "AFFECTS", "milestone:atlas-launch"),
    ("decision:beacon-november", "AFFECTS", "milestone:beacon-launch"),
    ("source:atlas-brief", "STATES", "claim:atlas-tuesday"),
    ("claim:atlas-tuesday", "SUPPORTED_BY", "decision:atlas-tuesday"),
    ("project:atlas", "HAS_MILESTONE", "milestone:atlas-launch"),
    ("project:atlas", "HAS_MILESTONE", "milestone:localization"),
    ("project:beacon", "HAS_MILESTONE", "milestone:beacon-launch"),
    ("milestone:atlas-launch", "DEPENDS_ON", "milestone:localization"),
    ("deliverable:launch-brief", "DEPENDS_ON", "milestone:atlas-launch"),
    ("deliverable:partner-announcement", "DEPENDS_ON", "deliverable:launch-brief"),
    ("deliverable:social-kit", "DEPENDS_ON", "milestone:atlas-launch"),
    ("deliverable:beacon-brief", "DEPENDS_ON", "milestone:beacon-launch"),
    ("commitment:partner-preview", "DEPENDS_ON", "deliverable:partner-announcement"),
    ("commitment:customer-webinar", "DEPENDS_ON", "deliverable:launch-brief"),
    ("source:atlas-brief", "OWNED_BY", "person:priya"),
    ("source:partner-plan", "OWNED_BY", "person:leo"),
    ("milestone:atlas-launch", "OWNED_BY", "person:maya"),
    ("deliverable:launch-brief", "OWNED_BY", "person:priya"),
    ("deliverable:partner-announcement", "OWNED_BY", "person:leo"),
    ("commitment:partner-preview", "OWNED_BY", "person:leo"),
    ("person:maya", "MEMBER_OF", "team:product"),
    ("person:priya", "MEMBER_OF", "team:marketing"),
    ("person:leo", "MEMBER_OF", "team:partnerships"),
]


def seed(reset: bool = False, graph_name: str | None = None) -> dict[str, int]:
    db = FalkorDB(host=settings.host, port=settings.port, username=settings.username,
                  password=settings.password, ssl=settings.ssl)
    graph = db.select_graph(graph_name or settings.graph)
    if reset:
        try:
            graph.delete()
        except Exception as exc:
            if "does not exist" not in str(exc).lower() and "empty key" not in str(exc).lower():
                raise
        graph = db.select_graph(graph_name or settings.graph)
    for label, node_id, name, props in NODES:
        graph.query(
            f"MERGE (n:{label} {{id: $id}}) ON CREATE SET n.name = $name, n += $props",
            {"id": node_id, "name": name, "props": props},
        )
    for source, rel, target in EDGES:
        graph.query(
            f"MATCH (a {{id: $source}}), (b {{id: $target}}) MERGE (a)-[:{rel}]->(b)",
            {"source": source, "target": target},
        )
    return {"nodes": len(NODES), "edges": len(EDGES)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    print(seed(reset=args.reset))
