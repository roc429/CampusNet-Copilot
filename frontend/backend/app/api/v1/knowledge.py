import os
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from neo4j import GraphDatabase

load_dotenv()

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

CYPHER_TOPOLOGY = """
MATCH (a)-[r]->(b)
RETURN
    id(a) AS source_internal_id,
    labels(a) AS source_labels,
    properties(a) AS source_props,
    id(r) AS rel_internal_id,
    type(r) AS relation,
    properties(r) AS rel_props,
    id(b) AS target_internal_id,
    labels(b) AS target_labels,
    properties(b) AS target_props
LIMIT 200
"""

CYPHER_ORPHAN_NODES = """
MATCH (n)
WHERE NOT (n)--()
RETURN
    id(n) AS internal_id,
    labels(n) AS labels,
    properties(n) AS properties
LIMIT 50
"""

IMPORT_CYPHER = [
    'MERGE (ap:Device {deviceID: "AP-EXAM-302", name: "302考场AP"})',
    'MERGE (sw:Switch {deviceID: "SW-EXAM-3F", name: "考试楼三层接入交换机"})',
    'MERGE (area:Area {name: "302考场"})',
    'MERGE (ap)-[:CONNECTED_TO]->(sw)',
    'MERGE (ap)-[:LOCATED_IN]->(area)',
]


def _node_id(props: dict[str, Any], internal_id: int) -> str:
    if props.get("deviceID"):
        return str(props["deviceID"])
    if props.get("name"):
        return str(props["name"])
    return str(internal_id)


def _node_payload(internal_id: int, labels: list[str], props: dict[str, Any]) -> dict[str, Any]:
    clean_props = {k: v for k, v in dict(props).items() if k != "_neo4j_id"}
    nid = _node_id(clean_props, internal_id)
    display = clean_props.get("name") or clean_props.get("deviceID") or nid
    ntype = labels[0] if labels else "Node"
    return {
        "id": nid,
        "label": str(display),
        "type": ntype,
        "properties": {**clean_props, "_neo4j_id": internal_id},
    }


@router.get("/topology")
def get_topology() -> dict[str, Any]:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法连接 Neo4j: {exc}") from exc

    nodes_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    raw_records: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}

    try:
        with driver.session() as session:
            result = session.run(CYPHER_TOPOLOGY)
            for record in result:
                src_internal = int(record["source_internal_id"])
                tgt_internal = int(record["target_internal_id"])
                src_props = dict(record["source_props"])
                tgt_props = dict(record["target_props"])
                src_labels = list(record["source_labels"] or [])
                tgt_labels = list(record["target_labels"] or [])
                relation = str(record["relation"])
                rel_props = dict(record["rel_props"] or {})
                rel_internal = int(record["rel_internal_id"])

                src_node = _node_payload(src_internal, src_labels, src_props)
                tgt_node = _node_payload(tgt_internal, tgt_labels, tgt_props)
                nodes_map[src_node["id"]] = src_node
                nodes_map[tgt_node["id"]] = tgt_node

                label_counts[src_node["type"]] = label_counts.get(src_node["type"], 0) + 1
                label_counts[tgt_node["type"]] = label_counts.get(tgt_node["type"], 0) + 1
                relation_counts[relation] = relation_counts.get(relation, 0) + 1

                edge_id = f"e{rel_internal}"
                edges.append({
                    "id": edge_id,
                    "source": src_node["id"],
                    "target": tgt_node["id"],
                    "relation": relation,
                    "properties": rel_props,
                })

                raw_records.append({
                    "source": src_node,
                    "relation": relation,
                    "target": tgt_node,
                    "rel_internal_id": rel_internal,
                })

            orphan_result = session.run(CYPHER_ORPHAN_NODES)
            for record in orphan_result:
                internal_id = int(record["internal_id"])
                labels = list(record["labels"] or [])
                props = dict(record["properties"])
                node = _node_payload(internal_id, labels, props)
                if node["id"] not in nodes_map:
                    nodes_map[node["id"]] = node
                    label_counts[node["type"]] = label_counts.get(node["type"], 0) + 1
    except Exception as exc:
        driver.close()
        raise HTTPException(status_code=503, detail=f"Neo4j 查询失败: {exc}") from exc

    driver.close()

    nodes = list(nodes_map.values())
    # 去重后的标签计数
    unique_label_counts: dict[str, int] = {}
    for node in nodes:
        unique_label_counts[node["type"]] = unique_label_counts.get(node["type"], 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_labels": sorted(unique_label_counts.keys()),
            "relationship_types": sorted(relation_counts.keys()),
            "node_counts": unique_label_counts,
            "relationship_counts": relation_counts,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        },
        "raw": {
            "cypher": {
                "topology": CYPHER_TOPOLOGY.strip(),
                "import_example": IMPORT_CYPHER,
            },
            "records": raw_records,
        },
    }
