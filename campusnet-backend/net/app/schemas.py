"""系统公共数据结构定义。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _event_id() -> str:
    return f"evt-{uuid4().hex}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


EventType = Literal[
    "user_network_status_query",
    "user_fault_report",
    "user_diagnosis_request",
    "prometheus_alert",
    "timesfm_forecast_anomaly",
    "scheduled_inspection_anomaly",
    "device_down",
    "interface_down",
    "interface_error_spike",
    "packet_loss_anomaly",
    "device_cpu_high",
    "device_memory_high",
    "ap_overload",
    "traffic_hotspot_warning",
    "link_congestion_forecast",
    "config_change_request",
    "high_risk_config_change",
    "unauthorized_device_detected",
    "illegal_vlan_change",
    "suspicious_admin_command",
    "policy_violation",
]

Severity = Literal["info", "warning", "critical", "unknown"]
RiskLevel = Literal["normal", "warning", "critical", "unknown"]


class AnomalyEvent(BaseModel):
    """需要后台诊断的结构化运维事件。

    保留旧遥测字段以兼容现有 TelemetryAgent，同时通过 event_type/source
    支持用户主动诊断、Prometheus 告警和未来预测异常等多来源事件。
    """

    event_id: str = Field(default_factory=_event_id)
    event_type: EventType | str = "prometheus_alert"
    source: str = "telemetry"
    user_id: str | None = None
    question: str | None = None
    timestamp: str = Field(default_factory=_utc_now_iso)
    location_hint: str | None = None
    device_id: str | None = None
    metric: str | None = None
    symptom: str | None = None
    severity: Severity = "unknown"
    status: str = "new"
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Legacy compatibility fields.
    location: str = ""
    issue_desc: str = ""
    packet_loss: float = 0.0
    latency_ms: float = 0.0
    device_hint: str = ""


class DiagnosisResult(BaseModel):
    """诊断智能体输出结果。"""

    event_id: str
    event_type: str = "unknown"
    source: str = "unknown"
    question: str | None = None
    location: str = ""
    issue_desc: str = ""
    summary: str = ""
    risk_level: RiskLevel = "unknown"
    evidence: dict[str, Any] = Field(default_factory=dict)
    possible_causes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    suspect_devices: list[str] = Field(default_factory=list)
    final_reasoning: str = ""


class OpsReport(BaseModel):
    """最终运维简报。"""

    event_id: str
    report_text: str
    event_type: str = "unknown"
    source: str = "unknown"
    timestamp: str = Field(default_factory=_utc_now_iso)


class ChatRequest(BaseModel):
    """前台客服问答请求。"""

    user_id: str = Field(..., description="用户 ID")
    question: str = Field(..., description="用户提问")


class ChatResponse(BaseModel):
    """前台客服问答响应。"""

    answer: str


class SecurityCheckRequest(BaseModel):
    """运维变更安全校验请求。"""

    user_id: str = Field(..., description="提交变更的用户或管理员")
    command: str = Field(..., description="自然语言或配置命令")
    target: str | None = Field(default=None, description="目标设备、接口或区域")


class SecurityDecision(BaseModel):
    """安全护栏对变更请求的判定。"""

    audit_id: str
    decision: Literal["allow", "approve_required", "blocked"]
    risk_level: RiskLevel
    reason: str
    affected_scope: list[str] = Field(default_factory=list)
    required_approval: bool = False
    matched_policies: list[str] = Field(default_factory=list)


class RemediationPlan(BaseModel):
    """自动修复/半自动修复计划。"""

    plan_id: str = Field(default_factory=lambda: f"plan-{uuid4().hex}")
    event_id: str
    risk_level: RiskLevel = "unknown"
    action_type: str = "manual_review"
    actions: list[str] = Field(default_factory=list)
    control_commands: list["ControlCommand"] = Field(default_factory=list)
    requires_approval: bool = True
    status: Literal["proposed", "approved", "blocked", "executed"] = "proposed"
    reason: str = ""


class ControlCommand(BaseModel):
    """准备下发到控制器或运维执行系统的结构化控制命令。"""

    command_id: str = Field(default_factory=lambda: f"cmd-{uuid4().hex}")
    command_type: str
    target: str
    command: str
    risk_level: RiskLevel = "unknown"
    requires_approval: bool = True
    dry_run: bool = True
    rationale: str = ""


class SDNCommandPayload(BaseModel):
    """SDN Controller Adapter 编译后的控制器负载。"""

    command_id: str
    command_type: str
    target: str
    controller: str = "mock-sdn-controller"
    protocol: str = "mock"
    operation: str
    dry_run: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    rollback: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlExecutionResult(BaseModel):
    """SDN Controller Adapter 执行结果。"""

    command_id: str
    command_type: str
    target: str
    command: str
    controller: str = "mock-sdn-controller"
    protocol: str = "mock"
    operation: str
    dry_run: bool = True
    status: str
    success: bool
    message: str
    compiled_payload: SDNCommandPayload


class RemediationClosure(BaseModel):
    """场景 1 闭环预执行结果。"""

    event_id: str
    plan: RemediationPlan
    security_decisions: list[SecurityDecision] = Field(default_factory=list)
    dispatchable_commands: list[ControlCommand] = Field(default_factory=list)
    approval_required_commands: list[ControlCommand] = Field(default_factory=list)
    blocked_commands: list[ControlCommand] = Field(default_factory=list)
    dispatch_status: Literal["ready_for_controller", "approval_required", "blocked", "no_command"]
    note: str = "当前阶段只确定待下发控制命令，不连接底层 SDN Controller。"


class ForecastQueryRequest(BaseModel):
    """按需预测请求。"""

    location: str | None = None
    device_ids: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=lambda: ["connections", "packet_loss", "cpu_load"])
    horizon_minutes: int = 1440
    freq: str = "30m"


class ApprovalRequest(BaseModel):
    """用户或管理员确认执行需审批命令。"""

    approved_by: str = "user"
    rejected_by: str | None = None


class MCPCallRequest(BaseModel):
    """统一 MCP 工具调用请求。"""

    server_name: str = Field(..., description="MCP server name, e.g. netbox/prometheus/timesfm/grafana")
    tool_name: str = Field(..., description="Remote MCP tool name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class OpsMetricsRequest(BaseModel):
    """实时网络遥测指标查询请求。"""

    device_id: str = Field(..., description="设备 ID 或设备名称")
    window: str = Field(default="5m", description="可选聚合窗口，默认 5m")


class OpsMetricsResponse(BaseModel):
    """面向 Agent 和前端的标准化实时指标响应。"""

    device_id: str
    ap_load: float | None = None
    packet_loss: float | None = None
    latency: float | None = None
    bandwidth_usage: float | None = None
    cpu_load: float | None = None
    connections: float | None = None
    timestamp: str = Field(default_factory=_utc_now_iso)
    source: str = "prometheus_mcp"
    missing_metrics: list[str] = Field(default_factory=list)
    raw_queries: dict[str, str] = Field(default_factory=dict)
