#!/usr/bin/env python3
"""FastAPI 拓扑图查询服务 —— 从 Neo4j 读取校园网拓扑，提供统一检索入口。"""
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# ── .env 必须在 neo4j import 之前加载 ──
load_dotenv(Path(__file__).parent / ".env")

from neo4j import GraphDatabase
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Neo4j 连接 ──────────────────────────────────
NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PWD  = os.getenv("NEO4J_PWD",  "password")

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
    return _driver


# ── FastAPI 应用 ────────────────────────────────
app = FastAPI(title="校园网拓扑 API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════
#  Pydantic 模型
# ═══════════════════════════════════════════════════

class UnifiedSearchRequest(BaseModel):
    query: str = Field(..., description="用户自然语言输入")
    device_id: str = Field(..., description="目标设备 ID，如 AP-EXAM-302")
    top_k: int = Field(default=5, description="Milvus 检索返回条数")


class TopologyLink(BaseModel):
    source: str
    relation: str
    target: str


class UnifiedSearchResponse(BaseModel):
    evidence_snapshot: str
    topology_chain: List[TopologyLink] = Field(default_factory=list)
    semantic_hits: List[str] = Field(default_factory=list)
    filtered_out: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════
#  核心逻辑
# ═══════════════════════════════════════════════════

def _format_node(neo_node):
    """将 Neo4j Node 转为 ECharts 节点格式。"""
    props = dict(neo_node)
    label = list(neo_node.labels)[0]
    node = {
        "id":       props.get("name", ""),
        "name":     props.get("name", ""),
        "category": label,
    }
    node.update(props)
    return node


def _fetch_full_topology():
    """查询全部节点和关系。"""
    with get_driver().session() as session:
        nodes_result = session.run("MATCH (n) RETURN n")
        nodes_map = {}
        all_nodes = []
        for record in nodes_result:
            node = _format_node(record["n"])
            name = node["name"]
            if name and name not in nodes_map:
                nodes_map[name] = node
                all_nodes.append(node)

        links_result = session.run(
            "MATCH (n)-[r]->(m) RETURN n.name AS src, m.name AS tgt, type(r) AS rel"
        )
        seen_links = set()
        links = []
        for record in links_result:
            src, tgt, rel = record["src"], record["tgt"], record["rel"]
            if not src or not tgt:
                continue
            key = (src, tgt, rel)
            if key not in seen_links:
                seen_links.add(key)
                links.append({"source": src, "target": tgt, "label": rel})

        categories_set = sorted(set(n["category"] for n in all_nodes if n["category"]))
        categories = [{"name": c} for c in categories_set]

        return {"nodes": all_nodes, "links": links, "categories": categories}


def _fetch_neighborhood(name: str):
    """查询以指定节点为中心的一跳邻域。"""
    with get_driver().session() as session:
        check = session.run(
            "MATCH (n {name: $name}) RETURN n LIMIT 1", name=name
        )
        center_record = check.single()
        if not center_record:
            return None

        nodes_map = {}
        center = _format_node(center_record["n"])
        nodes_map[center["name"]] = center

        rels_result = session.run(
            "MATCH (n {name: $name})-[r]-(m) RETURN n, r, m", name=name
        )
        seen_links = set()
        links = []

        for record in rels_result:
            n_node = _format_node(record["n"])
            m_node = _format_node(record["m"])
            nodes_map[n_node["name"]] = n_node
            nodes_map[m_node["name"]] = m_node

            rel_type = record["r"].type
            if n_node["name"] == name:
                key = (n_node["name"], m_node["name"], rel_type)
                if key not in seen_links:
                    seen_links.add(key)
                    links.append({"source": n_node["name"], "target": m_node["name"], "label": rel_type})
            else:
                key = (m_node["name"], n_node["name"], rel_type)
                if key not in seen_links:
                    seen_links.add(key)
                    links.append({"source": m_node["name"], "target": n_node["name"], "label": rel_type})

        all_nodes = list(nodes_map.values())
        categories_set = sorted(set(n["category"] for n in all_nodes if n.get("category")))
        categories = [{"name": c} for c in categories_set]

        return {"nodes": all_nodes, "links": links, "categories": categories}


# ═══════════════════════════════════════════════════
#  统一检索辅助函数
# ═══════════════════════════════════════════════════



def _get_hybrid_rag():
    """懒加载 HybridGraphRAG 实例。"""
    global _rag_instance
    if "_rag_instance" not in globals() or _rag_instance is None:
        from hybrid_retriever import HybridGraphRAG
        _rag_instance = HybridGraphRAG()
    return _rag_instance


# ═══════════════════════════════════════════════════
#  API 端点
# ═══════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "service": "校园网拓扑 API",
        "endpoints": {
            "/api/v1/health": "健康检查",
            "/api/v1/topology": "全量拓扑图",
            "/api/v1/topology/{name}": "单设备邻域子图",
            "POST /api/v1/unified-search": "统一检索入口",
        },
        "docs": "/docs",
    }


@app.get("/api/v1/health")
def health():
    try:
        get_driver().verify_connectivity()
        return {"status": "ok", "neo4j": NEO4J_URI}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 不可达: {e}")


@app.get("/api/v1/topology")
def full_topology():
    data = _fetch_full_topology()
    data["total_nodes"] = len(data["nodes"])
    data["total_links"] = len(data["links"])
    return data


@app.get("/api/v1/topology/{name}")
def device_neighborhood(name: str):
    data = _fetch_neighborhood(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f'设备 {name} 未找到')
    data["center"] = name
    data["total_nodes"] = len(data["nodes"])
    data["total_links"] = len(data["links"])
    return data


@app.post("/api/v1/unified-search", response_model=UnifiedSearchResponse)
def unified_search(req: UnifiedSearchRequest):
    """统一检索入口：混合检索 + 拓扑约束抗幻觉。"""
    rag = _get_hybrid_rag()
    result = rag.hybrid_search(req.query, req.device_id, top_k=req.top_k)

    return UnifiedSearchResponse(
        evidence_snapshot=result.get("evidence_snapshot", ""),
        topology_chain=result.get("topology_chain", []),
        semantic_hits=result.get("semantic_hits", []),
        filtered_out=result.get("filtered_out", []),
    )

# ═══════════════════════════════════════════════════
#  启动入口
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("topology_api:app", host="0.0.0.0", port=8001, reload=True)
