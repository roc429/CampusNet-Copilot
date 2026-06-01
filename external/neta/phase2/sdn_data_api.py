# -*- coding: utf-8 -*-
"""
SDN 数据接口层：证据快照 / 拓扑视图传入接口

本接口只负责接收上游已经完成检索、拓扑遍历、重排序之后的结构化结果。
不负责 Milvus 检索。
不负责 Neo4j 遍历。
不负责 BGE-M3 重排序。
不负责 LangGraph 状态机推理。

你的 SDN 模块只接收：
1. evidence_snapshot
2. evidence_snapshot.topology_view
"""

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


# =========================
# 基础配置
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

CURRENT_EVIDENCE_FILE = os.path.join(DATA_DIR, "current_evidence_snapshot.json")
EVIDENCE_HISTORY_FILE = os.path.join(DATA_DIR, "evidence_snapshot_history.jsonl")

CURRENT_TOPOLOGY_FILE = os.path.join(DATA_DIR, "current_topology_view.json")
TOPOLOGY_HISTORY_FILE = os.path.join(DATA_DIR, "topology_view_history.jsonl")


app = FastAPI(
    title="SDN Data Interface",
    description="校园网智能运维系统 SDN 数据接口层",
    version="0.1.0"
)


# =========================
# 统一接口模型
# =========================

class UnifiedContext(BaseModel):
    session_id: Optional[str] = None
    location: Optional[str] = None
    topology_version: Optional[str] = None
    request_id: Optional[str] = None
    langgraph_state_id: Optional[str] = None


class UnifiedResponse(BaseModel):
    task_id: str
    status: str
    module: str = "sdn"
    intent_type: str
    thinking_process: List[str]
    evidence_snapshot: Dict[str, Any]
    result: Dict[str, Any]
    simulation_id: Optional[str] = None
    timestamp_iso: str


class EvidenceImportRequest(BaseModel):
    """
    接收赵中赐模块 / LangGraph 状态机输出的结构化证据快照。

    注意：
    这里不接收 Neo4j 原始查询。
    这里不执行拓扑遍历。
    这里只接收已经整理好的 evidence_snapshot。
    """

    query: str = Field(
        default="导入上游混合检索模块生成的证据快照",
        description="统一接口中的自然语言任务描述"
    )

    user_role: str = Field(
        default="retrieval_engine",
        description="调用方角色，例如 retrieval_engine、agent、admin"
    )

    context: UnifiedContext = Field(
        default_factory=UnifiedContext,
        description="统一上下文信息"
    )

    evidence_snapshot: Dict[str, Any] = Field(
        ...,
        description="上游混合检索、拓扑遍历、重排序后生成的结构化证据快照"
    )


# =========================
# 工具函数
# =========================

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def new_task_id() -> str:
    return "task-" + str(uuid.uuid4())


def model_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


def save_json(path: str, data: Dict[str, Any]) -> None:
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_jsonl(path: str, data: Dict[str, Any]) -> None:
    ensure_data_dir()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def extract_topology_view(evidence_snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从 evidence_snapshot 中提取 SDN 可用拓扑视图。

    推荐上游直接提供：
    evidence_snapshot.topology_view

    如果没有 topology_view，本接口不主动从 graph_paths 或 text_evidence 中推理拓扑，
    因为那属于上游检索分析模块职责。
    """

    topology_view = evidence_snapshot.get("topology_view")

    if topology_view is None:
        return None

    if not isinstance(topology_view, dict):
        return None

    return topology_view


def validate_topology_view(topology_view: Dict[str, Any]) -> Dict[str, Any]:
    """
    校验 topology_view 是否满足 SDN 模块使用要求。

    SDN 最低需要：
    1. nodes
    2. links
    3. node.id
    4. link.src
    5. link.dst

    如果要和 Ryu 策略下发绑定，交换机节点最好包含 dpid。
    如果要和预测绑定，接入交换机最好包含 role / area。
    """

    if not isinstance(topology_view, dict):
        return {
            "passed": False,
            "reason": "topology_view must be a json object"
        }

    nodes = topology_view.get("nodes")
    links = topology_view.get("links")

    if nodes is None:
        return {
            "passed": False,
            "reason": "missing topology_view.nodes"
        }

    if links is None:
        return {
            "passed": False,
            "reason": "missing topology_view.links"
        }

    if not isinstance(nodes, list):
        return {
            "passed": False,
            "reason": "topology_view.nodes must be a list"
        }

    if not isinstance(links, list):
        return {
            "passed": False,
            "reason": "topology_view.links must be a list"
        }

    node_ids = []

    for node in nodes:
        if not isinstance(node, dict):
            return {
                "passed": False,
                "reason": "each node must be a json object"
            }

        node_id = node.get("id")
        if not node_id:
            return {
                "passed": False,
                "reason": "each node must contain id"
            }

        node_ids.append(str(node_id))

    duplicated = sorted({
        node_id for node_id in node_ids
        if node_ids.count(node_id) > 1
    })

    if duplicated:
        return {
            "passed": False,
            "reason": "duplicated node id",
            "duplicated_nodes": duplicated
        }

    node_id_set = set(node_ids)
    broken_links = []

    for link in links:
        if not isinstance(link, dict):
            return {
                "passed": False,
                "reason": "each link must be a json object"
            }

        src = str(link.get("src"))
        dst = str(link.get("dst"))

        if src not in node_id_set or dst not in node_id_set:
            broken_links.append(link)

    if broken_links:
        return {
            "passed": False,
            "reason": "link endpoint not found in nodes",
            "broken_links": broken_links
        }

    switches = [
        node for node in nodes
        if str(node.get("type", "")).lower() in {
            "switch",
            "core",
            "aggregation",
            "teaching_ap",
            "dorm_ap",
            "data_access"
        }
    ]

    switches_without_dpid = [
        node.get("id") for node in switches
        if node.get("dpid") is None
    ]

    return {
        "passed": True,
        "reason": "topology_view validation passed",
        "node_count": len(nodes),
        "link_count": len(links),
        "subnet_count": len(topology_view.get("subnets", [])),
        "switch_count": len(switches),
        "switches_without_dpid": switches_without_dpid,
        "warning": (
            "some switches do not contain dpid"
            if switches_without_dpid else None
        )
    }


def build_evidence_summary(
    evidence_snapshot: Dict[str, Any],
    topology_view: Optional[Dict[str, Any]],
    topology_validation: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    生成返回给统一接口的 evidence_snapshot。
    这里是接口处理证据，不是重新生成上游检索证据。
    """

    retrieval_modules = evidence_snapshot.get("retrieval_modules", [])
    graph_paths = evidence_snapshot.get("graph_paths", [])
    text_evidence = evidence_snapshot.get("text_evidence", [])

    if topology_view:
        node_count = len(topology_view.get("nodes", []))
        link_count = len(topology_view.get("links", []))
        subnet_count = len(topology_view.get("subnets", []))
    else:
        node_count = 0
        link_count = 0
        subnet_count = 0

    return {
        "timestamp_iso": now_iso(),
        "incoming_snapshot_id": evidence_snapshot.get("snapshot_id"),
        "incoming_source": evidence_snapshot.get("source"),
        "retrieval_modules": retrieval_modules,
        "reranker": evidence_snapshot.get("reranker"),
        "confidence": evidence_snapshot.get("confidence"),
        "graph_path_count": len(graph_paths) if isinstance(graph_paths, list) else None,
        "text_evidence_count": len(text_evidence) if isinstance(text_evidence, list) else None,
        "topology_view_found": topology_view is not None,
        "topology_validation": topology_validation,
        "node_count": node_count,
        "link_count": link_count,
        "subnet_count": subnet_count,
        "current_evidence_file": CURRENT_EVIDENCE_FILE,
        "current_topology_file": CURRENT_TOPOLOGY_FILE
    }


# =========================
# 健康检查
# =========================

@app.get("/v1/sdn/health")
def health():
    return {
        "ok": True,
        "service": "sdn-data-interface",
        "timestamp_iso": now_iso(),
        "current_evidence_loaded": os.path.exists(CURRENT_EVIDENCE_FILE),
        "current_topology_loaded": os.path.exists(CURRENT_TOPOLOGY_FILE),
        "current_evidence_file": CURRENT_EVIDENCE_FILE,
        "current_topology_file": CURRENT_TOPOLOGY_FILE
    }


# =========================
# 传入接口：证据快照导入
# =========================

@app.post("/v1/sdn/evidence/import", response_model=UnifiedResponse)
def import_evidence_snapshot(req: EvidenceImportRequest):
    """
    接收上游混合检索模块生成的证据快照。

    这个接口是 SDN 模块对上游拓扑遍历工作的输入口。

    上游职责：
    1. Milvus 密集语义召回
    2. Neo4j 拓扑遍历
    3. BGE-M3 重排序
    4. 生成 evidence_snapshot
    5. 在 evidence_snapshot 中给出 topology_view

    本接口职责：
    1. 接收 evidence_snapshot
    2. 提取 topology_view
    3. 校验 topology_view
    4. 保存证据快照
    5. 保存 SDN 当前拓扑视图
    """

    task_id = new_task_id()

    thinking_process = [
        "接收上游混合检索模块传入的 evidence_snapshot",
        "读取统一字段 query、user_role、context",
        "从 evidence_snapshot 中提取 topology_view",
        "校验 topology_view 是否满足 SDN 模块使用要求",
        "保存当前证据快照",
        "如果 topology_view 有效，则保存当前 SDN 拓扑视图"
    ]

    topology_view = extract_topology_view(req.evidence_snapshot)

    if topology_view is None:
        evidence_summary = build_evidence_summary(
            evidence_snapshot=req.evidence_snapshot,
            topology_view=None,
            topology_validation=None
        )

        record = {
            "task_id": task_id,
            "timestamp": time.time(),
            "timestamp_iso": now_iso(),
            "query": req.query,
            "user_role": req.user_role,
            "context": model_to_dict(req.context),
            "evidence_snapshot": req.evidence_snapshot,
            "status": "accepted_without_topology_view"
        }

        save_json(CURRENT_EVIDENCE_FILE, record)
        append_jsonl(EVIDENCE_HISTORY_FILE, record)

        return UnifiedResponse(
            task_id=task_id,
            status="accepted_pending",
            intent_type="evidence_import",
            thinking_process=thinking_process,
            evidence_snapshot=evidence_summary,
            result={
                "message": "已接收 evidence_snapshot，但其中没有 topology_view。SDN 模块无法生成当前拓扑视图。",
                "required_field": "evidence_snapshot.topology_view",
                "next_action": "请上游拓扑遍历模块在 evidence_snapshot 中补充 topology_view。"
            },
            simulation_id=None,
            timestamp_iso=now_iso()
        )

    topology_validation = validate_topology_view(topology_view)

    evidence_summary = build_evidence_summary(
        evidence_snapshot=req.evidence_snapshot,
        topology_view=topology_view,
        topology_validation=topology_validation
    )

    record = {
        "task_id": task_id,
        "timestamp": time.time(),
        "timestamp_iso": now_iso(),
        "query": req.query,
        "user_role": req.user_role,
        "context": model_to_dict(req.context),
        "evidence_snapshot": req.evidence_snapshot,
        "topology_view": topology_view,
        "topology_validation": topology_validation
    }

    save_json(CURRENT_EVIDENCE_FILE, record)
    append_jsonl(EVIDENCE_HISTORY_FILE, record)

    if not topology_validation["passed"]:
        return UnifiedResponse(
            task_id=task_id,
            status="rejected",
            intent_type="evidence_import",
            thinking_process=thinking_process,
            evidence_snapshot=evidence_summary,
            result={
                "message": "已接收 evidence_snapshot，但 topology_view 结构校验失败。",
                "validation": topology_validation
            },
            simulation_id=None,
            timestamp_iso=now_iso()
        )

    topology_record = {
        "task_id": task_id,
        "timestamp": time.time(),
        "timestamp_iso": now_iso(),
        "source_snapshot_id": req.evidence_snapshot.get("snapshot_id"),
        "source": req.evidence_snapshot.get("source"),
        "context": model_to_dict(req.context),
        "topology_view": topology_view,
        "topology_validation": topology_validation
    }

    save_json(CURRENT_TOPOLOGY_FILE, topology_record)
    append_jsonl(TOPOLOGY_HISTORY_FILE, topology_record)

    return UnifiedResponse(
        task_id=task_id,
        status="accepted",
        intent_type="evidence_import",
        thinking_process=thinking_process + [
            "topology_view 校验通过",
            "当前拓扑视图已更新",
            "证据快照历史已保存"
        ],
        evidence_snapshot=evidence_summary,
        result={
            "message": "evidence_snapshot 已成功导入，SDN 当前拓扑视图已更新。",
            "current_evidence_file": CURRENT_EVIDENCE_FILE,
            "current_topology_file": CURRENT_TOPOLOGY_FILE,
            "topology_validation": topology_validation
        },
        simulation_id=None,
        timestamp_iso=now_iso()
    )


# =========================
# 查询当前证据快照
# =========================

@app.get("/v1/sdn/evidence/current")
def get_current_evidence():
    if not os.path.exists(CURRENT_EVIDENCE_FILE):
        return {
            "ok": False,
            "message": "当前还没有导入 evidence_snapshot",
            "current_evidence_file": CURRENT_EVIDENCE_FILE
        }

    with open(CURRENT_EVIDENCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "ok": True,
        "timestamp_iso": now_iso(),
        "data": data
    }


# =========================
# 查询当前 SDN 拓扑视图
# =========================

@app.get("/v1/sdn/topology/current")
def get_current_topology_view():
    if not os.path.exists(CURRENT_TOPOLOGY_FILE):
        return {
            "ok": False,
            "message": "当前还没有可用的 topology_view",
            "current_topology_file": CURRENT_TOPOLOGY_FILE
        }

    with open(CURRENT_TOPOLOGY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "ok": True,
        "timestamp_iso": now_iso(),
        "data": data
    }