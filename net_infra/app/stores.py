"""In-memory stores for MVP task correlation and admin views."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.schemas import AnomalyEvent, DiagnosisResult, OpsReport, RemediationClosure, RemediationPlan, SecurityDecision


@dataclass
class OpsMemoryStore:
    """Small process-local store.

    This keeps queues as transport and gives APIs stable lookup by event_id.
    Replace with PostgreSQL/Redis when the MVP moves beyond a single process.
    """

    events: dict[str, AnomalyEvent] = field(default_factory=dict)
    diagnosis_results: dict[str, DiagnosisResult] = field(default_factory=dict)
    reports: dict[str, OpsReport] = field(default_factory=dict)
    latest_report_id: str | None = None
    latest_chat_event_by_user: dict[str, str] = field(default_factory=dict)
    forecast_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    forecast_locks: set[str] = field(default_factory=set)
    remediation_plans: dict[str, RemediationPlan] = field(default_factory=dict)
    remediation_closures: dict[str, RemediationClosure] = field(default_factory=dict)
    audit_logs: dict[str, SecurityDecision] = field(default_factory=dict)
    task_progress: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    task_status: dict[str, str] = field(default_factory=dict)
    approval_events: dict[str, asyncio.Event] = field(default_factory=dict)
    approval_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def save_event(self, event: AnomalyEvent) -> None:
        self.events[event.event_id] = event
        self.task_status[event.event_id] = "queued"
        self.add_progress(event.event_id, "queued", "诊断任务已创建，等待后台处理。")
        if event.source == "chat" and event.user_id:
            self.latest_chat_event_by_user[event.user_id] = event.event_id

    def save_diagnosis(self, result: DiagnosisResult) -> None:
        self.diagnosis_results[result.event_id] = result

    def save_report(self, report: OpsReport) -> None:
        self.reports[report.event_id] = report
        self.latest_report_id = report.event_id

    def save_forecast(self, key: str, payload: dict[str, Any]) -> None:
        self.forecast_results[key] = payload

    def save_remediation_plan(self, plan: RemediationPlan) -> None:
        self.remediation_plans[plan.plan_id] = plan

    def save_remediation_closure(self, closure: RemediationClosure) -> None:
        self.remediation_closures[closure.event_id] = closure

    def save_audit(self, decision: SecurityDecision) -> None:
        self.audit_logs[decision.audit_id] = decision

    def add_progress(self, event_id: str, stage: str, message: str, status: str = "running") -> None:
        self.task_progress.setdefault(event_id, []).append(
            {
                "stage": stage,
                "message": message,
                "status": status,
            }
        )
        if status in {"running", "waiting_approval", "completed", "failed"}:
            self.task_status[event_id] = status

    def approval_event(self, event_id: str) -> asyncio.Event:
        event = self.approval_events.get(event_id)
        if event is None:
            event = asyncio.Event()
            self.approval_events[event_id] = event
        return event

    def approve(self, event_id: str, approved_by: str = "user") -> None:
        self.approval_decisions[event_id] = {"approved": True, "approved_by": approved_by}
        self.add_progress(event_id, "approval", f"{approved_by} 已确认执行需审批命令。", "running")
        self.approval_event(event_id).set()

    def reject(self, event_id: str, rejected_by: str = "user") -> None:
        self.approval_decisions[event_id] = {"approved": False, "rejected_by": rejected_by}
        self.add_progress(event_id, "approval_rejected", f"{rejected_by} 已拒绝执行需审批命令。", "running")
        self.approval_event(event_id).set()
