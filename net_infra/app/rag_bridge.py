"""NMB Hybrid GraphRAG 桥接 —— 让 Agent 能调 NMB API。"""
import httpx
import logging

logger = logging.getLogger(__name__)
NMB_API = "http://localhost:8001/api/v1"

async def rag_hybrid_search(query: str, device_id: str, top_k: int = 5) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{NMB_API}/unified-search",
                json={"query": query, "device_id": device_id, "top_k": top_k},
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("semantic_hits", [])
            return {
                "ok": True,
                "evidence_snapshot": data.get("evidence_snapshot", ""),
                "topology_chain": data.get("topology_chain", []),
                "semantic_hits": hits if isinstance(hits, list) else [],
                "filtered_out": data.get("filtered_out", []),
                "source": "NMB_Hybrid_GraphRAG",
            }
    except Exception as exc:
        logger.error("RAG 检索失败: %s", exc)
        return {"ok": False, "error": str(exc), "evidence_snapshot": ""}
