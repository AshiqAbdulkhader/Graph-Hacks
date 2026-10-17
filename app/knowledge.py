"""Workspace-scoped graph ingestion, exploration, retrieval and provenance."""
from __future__ import annotations

import hashlib
import json
import re
import difflib
from typing import Any

from falkordb import FalkorDB
from falkordb.node import Node
from falkordb.edge import Edge

from app.config import settings
from app.control import now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def serial(value: Any):
    if isinstance(value, Node):
        return {"kind": "node", "internal_id": value.id, "labels": value.labels, **value.properties}
    if isinstance(value, Edge):
        return {"kind": "edge", "internal_id": value.id, "type": value.relation,
                "source": value.src_node, "target": value.dest_node, **value.properties}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    return value


class Knowledge:
    def __init__(self, graph_name: str):
        self.graph_name = graph_name
        self.graph = FalkorDB(host=settings.host, port=settings.port, username=settings.username,
                              password=settings.password, ssl=settings.ssl,
                              socket_timeout=15, socket_connect_timeout=5).select_graph(graph_name)

    def read(self, query: str, params: dict | None = None, timeout: int = 3000) -> list[dict]:
        result = self.graph.ro_query(query, params or {}, timeout=timeout)
        names = [h[1] for h in result.header]
        return [{k: serial(v) for k, v in zip(names, row)} for row in result.result_set]

    def write(self, query: str, params: dict | None = None):
        return self.graph.query(query, params or {})

    def initialize(self):
        self.write("MERGE (w:Workspace {id: $id}) SET w.name='Company workspace'", {"id": self.graph_name})
        for label in ("Entity", "Document", "Chunk", "DocumentVersion"):
            self.write(f"CREATE INDEX FOR (n:{label}) ON (n.id)")

    def stats(self):
        counts = self.read("MATCH (n) RETURN count(n) AS nodes")[0]
        counts["edges"] = self.read("MATCH ()-[r]->() RETURN count(r) AS edges")[0]["edges"]
        counts["labels"] = self.read("MATCH (n) UNWIND labels(n) AS label RETURN label,count(*) AS count ORDER BY count DESC")
        counts["relations"] = self.read("MATCH ()-[r]->() RETURN type(r) AS type,count(r) AS count ORDER BY count DESC")
        return counts

    def document(self, source: dict, text: str, chunks: list[str]) -> tuple[str, bool]:
        version_hash = hashlib.sha256(text.encode()).hexdigest()
        version_id = f"version:{source['id']}:{version_hash[:16]}"
        existing = self.read("MATCH (d:Document {id:$id}) OPTIONAL MATCH (d)-[:HAS_VERSION]->(v:DocumentVersion {active:true}) RETURN d.current_hash AS hash,count(v) AS active_versions", {"id": source["id"]})
        if existing and existing[0]["hash"] == version_hash and existing[0]["active_versions"]:
            return version_id, False
        self.write("MATCH (d:Document {id:$id})-[:HAS_VERSION]->(v:DocumentVersion) SET v.active=false", {"id": source["id"]})
        self.write("MATCH ()-[r:RELATED_TO {source_id:$id}]->() SET r.active=false", {"id": source["id"]})
        self.write(
            "MERGE (d:Document {id:$id}) SET d.name=$name,d.kind=$kind,d.uri=$uri,d.current_hash=$hash,d.updated_at=$at "
            "MERGE (v:DocumentVersion {id:$version_id}) SET v.hash=$hash,v.name=$version_name,v.active=true,v.recorded_at=$at "
            "MERGE (d)-[:HAS_VERSION]->(v)",
            {"id": source["id"], "name": source["title"], "kind": source["kind"], "uri": source.get("uri", ""),
             "hash": version_hash, "at": now(), "version_id": version_id, "version_name": source["title"] + " · " + version_hash[:7]},
        )
        for i, text_chunk in enumerate(chunks):
            self.write(
                "MATCH (v:DocumentVersion {id:$version_id}) MERGE (c:Chunk {id:$id}) "
                "SET c.name=$name,c.text=$text,c.position=$position,c.source_id=$source_id "
                "MERGE (v)-[:HAS_CHUNK]->(c)",
                {"version_id": version_id, "id": f"chunk:{version_id}:{i}", "name": f"Passage {i + 1}",
                 "text": text_chunk, "position": i, "source_id": source["id"]},
            )
        return version_id, True

    def entity(self, key: str, name: str, kind: str = "Concept", props: dict | None = None):
        kind = re.sub(r"[^A-Za-z0-9_]", "", kind)[:40] or "Concept"
        if not kind[0].isalpha():
            kind = "Type" + kind
        safe = {str(k): v for k, v in (props or {}).items() if isinstance(v, (str, int, float, bool)) and k not in {"id", "name"}}
        self.write(f"MERGE (n:Entity:{kind} {{id:$id}}) SET n.name=$name,n += $props", {"id": key, "name": name[:500], "props": safe})

    def relation(self, subject: str, target: str, predicate: str, source_id: str, version_id: str, quote: str = ""):
        predicate = re.sub(r"[^A-Z0-9_]", "_", predicate.upper())[:60] or "RELATED_TO"
        rel_id = digest(f"{subject}|{target}|{predicate}|{version_id}")
        self.write(
            "MATCH (a:Entity {id:$subject}),(b:Entity {id:$target}) "
            "MERGE (a)-[r:RELATED_TO {id:$rel_id}]->(b) "
            "SET r.predicate=$predicate,r.source_id=$source_id,r.version_id=$version_id,r.quote=$quote,r.active=true",
            {"subject": subject, "target": target, "rel_id": rel_id, "predicate": predicate,
             "source_id": source_id, "version_id": version_id, "quote": quote[:1500]},
        )

    def mention(self, entity_id: str, version_id: str, position: int = 0):
        self.write("MATCH (e:Entity {id:$id}),(c:Chunk {id:$chunk}) MERGE (e)-[:MENTIONED_IN]->(c)",
                   {"id": entity_id, "chunk": f"chunk:{version_id}:{position}"})

    def explore(self, search: str = "", label: str = "", limit: int = 300, offset: int = 0, visible: list[int] | None = None):
        limit = min(max(limit, 1), 1000)
        rows = self.read(
            "MATCH (n) WHERE ($search='' OR toLower(coalesce(n.name,'')) CONTAINS toLower($search)) "
            "AND ($label='' OR $label IN labels(n)) "
            "RETURN n ORDER BY n.id SKIP $offset LIMIT $limit",
            {"search": search[:200], "label": label[:50], "offset": max(offset, 0), "limit": limit},
        )
        nodes = [r["n"] for r in rows]
        ids = list(set([n["internal_id"] for n in nodes] + (visible or [])[:10000]))
        edges = self.read(
            "MATCH (a)-[r]->(b) WHERE id(a) IN $ids AND id(b) IN $ids "
            "RETURN id(r) AS id,id(a) AS source,id(b) AS target,type(r) AS type, "
            "r.predicate AS predicate,r.quote AS quote,r.active AS active LIMIT 4000", {"ids": ids},
        ) if ids else []
        return {"nodes": nodes, "edges": edges, "offset": offset, "limit": limit, "has_more": len(nodes) == limit}

    def neighbors(self, entity_id: str):
        rows = self.read("MATCH (n {id:$id})-[r]-(m) RETURN n,r,m LIMIT 150", {"id": entity_id})
        nodes, edges = {}, {}
        for row in rows:
            for key in ("n", "m"):
                nodes[row[key]["internal_id"]] = row[key]
            r = row["r"]
            edges[r["internal_id"]] = {"id": r["internal_id"], "source": r["source"], "target": r["target"],
                                       "type": r["type"], "predicate": r.get("predicate"), "active": r.get("active")}
        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    def search(self, query: str, limit: int = 8):
        tokens = list(dict.fromkeys(re.findall(r"[\w-]{3,}", query.lower())))[:12]
        ignored = {"what", "which", "where", "when", "does", "this", "that", "with", "from", "have", "about", "please", "show", "tell", "the", "and", "are", "can", "who"}
        tokens = [t for t in tokens if t not in ignored] or tokens[:2]
        if not tokens:
            return []
        terms = " + ".join(f"CASE WHEN toLower(c.text) CONTAINS $t{i} THEN 1 ELSE 0 END" for i in range(len(tokens)))
        params = {f"t{i}": token for i, token in enumerate(tokens)} | {"limit": min(max(limit, 1), 20)}
        return self.read(
            "MATCH (d:Document)-[:HAS_VERSION]->(v:DocumentVersion {active:true})-[:HAS_CHUNK]->(c:Chunk) "
            f"WITH d,c,({terms}) AS score WHERE score > 0 "
            "OPTIONAL MATCH (e:Entity)-[:MENTIONED_IN]->(c) "
            "RETURN d.id AS source_id,d.name AS title,d.uri AS uri,c.id AS chunk_id,c.text AS text,"
            "score,collect(DISTINCT e.id) AS entities ORDER BY score DESC LIMIT $limit", params,
        )

    def entity_search(self, query: str):
        return self.read("MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($query) RETURN e LIMIT 15", {"query": query[:200]})

    def expand(self, entity_id: str, depth: int = 2):
        depth = min(max(depth, 1), 3)
        return self.read(
            f"MATCH p=(a:Entity {{id:$id}})-[:RELATED_TO*1..{depth}]-(b:Entity) "
            "WHERE all(r IN relationships(p) WHERE r.active = true) "
            "RETURN [n IN nodes(p)|n.name] AS path,[r IN relationships(p)|r.predicate] AS relations,"
            "[r IN relationships(p)|r.source_id] AS source_ids, [r IN relationships(p)|r.active] AS active LIMIT 30",
            {"id": entity_id},
        )

    def history(self, source_id: str):
        return self.read("MATCH (d:Document {id:$id})-[:HAS_VERSION]->(v) RETURN d.name AS title,v.hash AS hash,v.recorded_at AS recorded_at,v.active AS active ORDER BY recorded_at DESC", {"id": source_id})

    def version_text(self, source_id: str, version_hash: str):
        rows = self.read("MATCH (d:Document {id:$id})-[:HAS_VERSION]->(v:DocumentVersion {hash:$hash})-[:HAS_CHUNK]->(c) RETURN c.text AS text,c.position AS position ORDER BY position", {"id": source_id,"hash":version_hash})
        if not rows:
            raise ValueError("Source version not found")
        # Passage windows overlap by 180 characters.
        return rows[0]["text"] + "".join(row["text"][180:] for row in rows[1:])

    def compare_versions(self, source_id: str, before_hash: str):
        versions = self.history(source_id)
        current = next((v for v in versions if v["active"]), None)
        if not current:
            raise ValueError("No current version to compare")
        before = self.version_text(source_id, before_hash)
        after = self.version_text(source_id, current["hash"])
        lines = list(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile=before_hash[:12],tofile=current["hash"][:12],lineterm=""))
        entities=self.read("MATCH (d:Document {id:$id})-[:HAS_VERSION]->(v)-[:HAS_CHUNK]->(c)<-[:MENTIONED_IN]-(e:Entity) RETURN DISTINCT e.id AS id,e.name AS name LIMIT 50",{"id":source_id})
        return {"before_hash":before_hash,"after_hash":current["hash"],"lines":lines[:2000],"truncated":len(lines)>2000,
                "added":sum(line.startswith('+') and not line.startswith('+++') for line in lines),
                "removed":sum(line.startswith('-') and not line.startswith('---') for line in lines),"related_entities":entities}

    def dependency_impact(self, entity_id: str, depth: int = 3):
        depth = min(max(depth,1),3)
        return self.read(
            f"MATCH p=(dependent:Entity)-[:RELATED_TO*1..{depth}]->(root:Entity {{id:$id}}) "
            "WHERE all(r IN relationships(p) WHERE r.active=true AND r.predicate IN ['DEPENDS_ON','PART_OF','IN_REPOSITORY','USES','REQUIRES','BLOCKED_BY']) "
            "RETURN dependent.id AS id,dependent.name AS name,[n IN nodes(p)|n.name] AS path,"
            "[r IN relationships(p)|r.predicate] AS relations,[r IN relationships(p)|r.source_id] AS source_ids,length(p) AS hops "
            "ORDER BY hops LIMIT 50", {"id":entity_id},
        )

    def relationship_changes(self, source_id: str):
        """Compare relationships declared by the current version of a source with all earlier versions."""
        rows = self.read(
            "MATCH (a:Entity)-[r:RELATED_TO {source_id:$id}]->(b:Entity) "
            "RETURN a.id AS subject_id,a.name AS subject,r.predicate AS predicate,b.id AS object_id,b.name AS object,"
            "r.version_id AS version_id,r.active AS active,r.quote AS quote", {"id": source_id})
        key = lambda r: (r["subject_id"], r["predicate"], r["object_id"])
        current = {key(r): r for r in rows if r["active"]}
        earlier = {key(r): r for r in rows if not r["active"]}
        added = [r for k, r in current.items() if k not in earlier]
        removed = [r for k, r in earlier.items() if k not in current]
        return {"added": added[:100], "removed": removed[:100]}

    def conflict_candidates(self):
        """Same subject and predicate pointing at different objects in different active sources.

        Cardinality is unknown, so these are candidates for review, each with its source quotes."""
        rows = self.read(
            "MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity) WHERE r.active=true "
            "RETURN a.id AS subject_id,a.name AS subject,r.predicate AS predicate,b.id AS object_id,b.name AS object,"
            "r.source_id AS source_id,r.quote AS quote LIMIT 5000")
        groups: dict = {}
        for r in rows:
            groups.setdefault((r["subject_id"], r["predicate"]), []).append(r)
        found = []
        for (subject_id, predicate), items in groups.items():
            if len({i["object_id"] for i in items}) < 2 or len({i["source_id"] for i in items}) < 2:
                continue
            # A claim is only in tension with claims from other sources.
            if all(len({j["source_id"] for j in items if j["object_id"] == i["object_id"]}) == len({j["source_id"] for j in items}) for i in items):
                continue
            titles = {d["id"]: d["name"] for d in self.read("MATCH (d:Document) RETURN d.id AS id,d.name AS name")}
            found.append({"subject_id": subject_id, "subject": items[0]["subject"], "predicate": predicate,
                          "claims": [{"object": i["object"], "object_id": i["object_id"], "source_id": i["source_id"],
                                      "source": titles.get(i["source_id"], i["source_id"]), "quote": i["quote"]} for i in items[:10]]})
        return found[:50]

    def tasks(self):
        return self.read("MATCH (t:Task)-[:SUPPORTED_BY]->(d:Document) RETURN t.id AS id,t.name AS title,t.status AS status,t.reason AS reason,t.approved_by AS approved_by,d.id AS source_id,d.name AS source ORDER BY title LIMIT 200")

    def source_remove(self, source_id: str):
        self.write("MATCH (d:Document {id:$id})-[:HAS_VERSION]->(v) SET v.active=false", {"id": source_id})
        self.write("MATCH ()-[r:RELATED_TO {source_id:$id}]->() SET r.active=false", {"id": source_id})

    def query(self, cypher: str):
        if len(cypher) > 12000:
            raise ValueError("Query is too long")
        # The database read-only command is the authority; results are capped in transport too.
        rows = self.read(cypher, timeout=2000)
        return {"rows": rows[:500], "truncated": len(rows) > 500}
