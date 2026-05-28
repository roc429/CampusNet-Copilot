"""SecurityGuardAgent: pre-change risk assessment and audit."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.schemas import SecurityCheckRequest, SecurityDecision
from app.stores import OpsMemoryStore


class SecurityGuardAgent:
    """Lightweight semantic guardrail for network change requests.

    This MVP uses deterministic policies. A later version can add LLM
    classification, but the final decision should still be policy-bound.
    """

    high_risk_keywords = ["核心", "core", "上联", "删除路由", "清空", "所有端口", "绕过认证", "放开所有", "disable all"]
    medium_risk_keywords = [
        "关闭",
        "shutdown",
        "重启",
        "修改",
        "vlan",
        "acl",
        "trunk",
        "qos",
        "rebalance",
        "failover",
        "切换",
        "调整",
        "poe",
        "power_cycle",
        "client_balance",
    ]
    suspicious_keywords = ["绕过", "非法", "隐藏", "不留记录", "跳过审批"]

    def __init__(self, store: OpsMemoryStore | None = None) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    async def assess(self, request: SecurityCheckRequest) -> SecurityDecision:
        text = f"{request.command} {request.target or ''}".lower()
        matched: list[str] = []
        affected_scope: list[str] = []

        if any(keyword.lower() in text for keyword in self.suspicious_keywords):
            matched.append("semantic.suspicious_operation")
        if any(keyword.lower() in text for keyword in self.high_risk_keywords):
            matched.append("topology.high_risk_core_or_broad_change")
            affected_scope.extend(["核心网络", "多区域业务"])
        if any(keyword.lower() in text for keyword in self.medium_risk_keywords):
            matched.append("change.medium_risk_network_config")

        if "sw-core" in text or "core" in text or "核心" in text:
            matched.append("asset.core_device_protection")
            affected_scope.append("核心设备")

        if any(policy.startswith(("semantic.", "topology.", "asset.")) for policy in matched):
            decision = "blocked"
            risk_level = "critical"
            reason = "命中高危或可疑变更策略，禁止自动执行。"
            required_approval = True
        elif matched:
            decision = "approve_required"
            risk_level = "warning"
            reason = "该变更可能影响网络配置，需要人工审批后执行。"
            required_approval = True
        else:
            decision = "allow"
            risk_level = "normal"
            reason = "未命中高危变更策略，可进入后续执行或低风险自动化流程。"
            required_approval = False

        result = SecurityDecision(
            audit_id=f"audit-{uuid4().hex}",
            decision=decision,  # type: ignore[arg-type]
            risk_level=risk_level,  # type: ignore[arg-type]
            reason=reason,
            affected_scope=list(dict.fromkeys(affected_scope)),
            required_approval=required_approval,
            matched_policies=list(dict.fromkeys(matched)),
        )
        if self.store is not None:
            self.store.save_audit(result)
        self.logger.info(
            "Security decision audit_id=%s decision=%s risk=%s",
            result.audit_id,
            result.decision,
            result.risk_level,
        )
        return result
