import json
from hybrid_retriever import HybridGraphRAG
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

rag = HybridGraphRAG()

results = []

cases = [
    {"query": "302考场考试系统卡顿，是不是AP负载太高？", "device_id": "AP-EXAM-302"},
    {"query": "401考场考生登录失败，考试系统无法访问", "device_id": "AP-EXAM-401"},
    {"query": "核心交换机CPU异常，影响哪些业务？", "device_id": "OF-CORE-01"},
    {"query": "XY-999设备故障", "device_id": "XY-999"},
]

for case in cases:
    r = rag.hybrid_search(case["query"], case["device_id"])
    results.append({
        "query": case["query"],
        "device_id": case["device_id"],
        "evidence_count": len(r["evidence"]),
        "evidence": r["evidence"],
        "context": r["context"],
    })

print(json.dumps(results, ensure_ascii=False, indent=2))
