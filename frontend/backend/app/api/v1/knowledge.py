import os
from fastapi import APIRouter
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/topology")
def get_topology():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))

    query = """
    MATCH (a)-[r]->(b)
    RETURN
        id(a) AS source_id,
        labels(a) AS source_labels,
        properties(a) AS source_props,
        type(r) AS relation,
        id(b) AS target_id,
        labels(b) AS target_labels,
        properties(b) AS target_props
    LIMIT 100
    """

    nodes = {}
    edges = []

    with driver.session() as session:
        result = session.run(query)

        for record in result:
            source_id = str(record["source_id"])
            target_id = str(record["target_id"])

            nodes[source_id] = {
                "id": source_id,
                "label": record["source_props"].get("name")
                or record["source_props"].get("deviceID")
                or source_id,
                "type": record["source_labels"][0] if record["source_labels"] else "Node",
                "properties": dict(record["source_props"]),
            }

            nodes[target_id] = {
                "id": target_id,
                "label": record["target_props"].get("name")
                or record["target_props"].get("deviceID")
                or target_id,
                "type": record["target_labels"][0] if record["target_labels"] else "Node",
                "properties": dict(record["target_props"]),
            }

            edges.append({
                "source": source_id,
                "target": target_id,
                "relation": record["relation"],
            })

    driver.close()

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }
