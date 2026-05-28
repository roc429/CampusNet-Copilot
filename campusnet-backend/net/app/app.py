"""CampusNet Copilot 新版后端入口(Macro-Async + Micro-LangGraph)。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agents.chat_agent import ChatAgent
from app.agents.diagnosis_agent import DiagnosisAgent
from app.agents.forecast_agent import ForecastAgent
from app.agents.remediation_agent import RemediationAgent
from app.agents.reporting_agent import ReportingAgent
from app.agents.security_guard_agent import SecurityGuardAgent
from app.agents.telemetry_agent import TelemetryAgent
from app.config import settings
from app.schemas import (
    AnomalyEvent,
    ApprovalRequest,
    ChatRequest,
    ChatResponse,
    DiagnosisResult,
    ForecastQueryRequest,
    OpsReport,
    RemediationClosure,
    RemediationPlan,
    SecurityCheckRequest,
    SecurityDecision,
)
from app.stores import OpsMemoryStore

# ----------------------------
# 核心队列（按需求定义在 app.py）
# ----------------------------
anomaly_queue: asyncio.Queue[AnomalyEvent] = asyncio.Queue()
diagnosis_queue: asyncio.Queue[DiagnosisResult] = asyncio.Queue()
report_queue: asyncio.Queue[OpsReport] = asyncio.Queue()
store = OpsMemoryStore()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期：启动并托管 4 个异步智能体任务。"""

    telemetry_agent = TelemetryAgent(anomaly_queue=anomaly_queue, interval_seconds=5, store=store)
    forecast_agent = ForecastAgent(
        anomaly_queue=anomaly_queue,
        store=store,
        interval_seconds=settings.forecast_interval_seconds,
    )
    diagnosis_agent = DiagnosisAgent(
        anomaly_queue=anomaly_queue,
        diagnosis_queue=diagnosis_queue,
        store=store,
    )
    reporting_agent = ReportingAgent(
        diagnosis_queue=diagnosis_queue,
        report_queue=report_queue,
        store=store,
    )
    chat_agent = ChatAgent(anomaly_queue=anomaly_queue, store=store)
    security_guard_agent = SecurityGuardAgent(store=store)
    remediation_agent = RemediationAgent(store=store)

    tasks = [
        asyncio.create_task(telemetry_agent.run(), name="telemetry-agent"),
        asyncio.create_task(forecast_agent.run(), name="forecast-agent"),
        asyncio.create_task(diagnosis_agent.run(), name="diagnosis-agent"),
        asyncio.create_task(reporting_agent.run(), name="reporting-agent"),
    ]

    app.state.chat_agent = chat_agent
    app.state.forecast_agent = forecast_agent
    app.state.security_guard_agent = security_guard_agent
    app.state.remediation_agent = remediation_agent
    app.state.store = store
    app.state.tasks = tasks
    app.state.latest_report = None
    app.state.latest_chat_report = None
    app.state.reports_by_event_id = {}

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="CampusNet Copilot Backend",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查。"""

    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    """Frontend test console."""

    return FileResponse("app/static/index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """前台客服接口：直接走 ChatAgent,不经过诊断队列。"""

    answer = await app.state.chat_agent.answer(user_id=req.user_id, question=req.question)
    return ChatResponse(answer=answer)


@app.get("/pipeline/stats")
async def pipeline_stats() -> dict[str, int]:
    """查看队列堆积情况。"""

    return {
        "anomaly_queue_size": anomaly_queue.qsize(),
        "diagnosis_queue_size": diagnosis_queue.qsize(),
        "report_queue_size": report_queue.qsize(),
        "event_store_size": len(store.events),
        "report_store_size": len(store.reports),
        "forecast_store_size": len(store.forecast_results),
    }


def _drain_report_queue() -> None:
    while not report_queue.empty():
        report = report_queue.get_nowait()
        report_queue.task_done()
        store.save_report(report)
        app.state.latest_report = report
        if report.source == "chat":
            app.state.latest_chat_report = report


@app.get("/reports/latest")
async def latest_report() -> dict[str, str]:
    """读取最新报告。

    为保持示例简单，接口会尝试从 `report_queue` 非阻塞地取出一条报告，
    并缓存为 latest_report。
    """

    # TODO: /reports/latest 只适合 MVP。后续应实现 /reports/{event_id}，
    # 避免多用户、多任务场景下报告混淆。
    _drain_report_queue()

    latest_chat_event_id = getattr(app.state.chat_agent, "latest_diagnosis_event_id", None)
    if latest_chat_event_id:
        latest_for_event = store.reports.get(latest_chat_event_id)
        if latest_for_event is not None:
            return {
                "event_id": latest_for_event.event_id,
                "report_text": latest_for_event.report_text,
            }
        raise HTTPException(status_code=404, detail=f"诊断报告仍在生成：{latest_chat_event_id}")

    latest = app.state.latest_chat_report or app.state.latest_report
    if latest is None:
        raise HTTPException(status_code=404, detail="暂无可读报告")

    return {"event_id": latest.event_id, "report_text": latest.report_text}


@app.get("/reports/{event_id}")
async def report_by_event_id(event_id: str) -> dict[str, str]:
    """按 event_id 精确读取报告，避免后台报告和用户报告混淆。"""

    _drain_report_queue()
    report = store.reports.get(event_id)
    if report is None:
        if event_id in store.events:
            raise HTTPException(status_code=404, detail=f"诊断报告仍在生成：{event_id}")
        raise HTTPException(status_code=404, detail=f"未找到任务：{event_id}")
    return {"event_id": report.event_id, "report_text": report.report_text}


@app.get("/tasks/{event_id}/status")
async def task_status(event_id: str) -> dict[str, object]:
    """轮询任务进度，供前端展示诊断/修复阶段。"""

    _drain_report_queue()
    event = store.events.get(event_id)
    report = store.reports.get(event_id)
    closure = store.remediation_closures.get(event_id)
    if event is None and report is None:
        raise HTTPException(status_code=404, detail=f"未找到任务：{event_id}")
    approval_required = False
    approval_commands = []
    if closure is not None:
        approval_required = bool(closure.approval_required_commands)
        approval_commands = [command.model_dump() for command in closure.approval_required_commands]
    return {
        "event_id": event_id,
        "status": store.task_status.get(event_id, "unknown"),
        "progress": store.task_progress.get(event_id, []),
        "approval_required": approval_required and event_id not in store.approval_decisions,
        "approval_commands": approval_commands,
        "report_ready": report is not None,
        "report_text": report.report_text if report is not None else None,
    }


@app.post("/tasks/{event_id}/approve")
async def approve_task(event_id: str, req: ApprovalRequest) -> dict[str, str]:
    """确认执行需审批控制命令，唤醒等待中的 DiagnosisAgent。"""

    if event_id not in store.events and event_id not in store.diagnosis_results:
        raise HTTPException(status_code=404, detail=f"未找到任务：{event_id}")
    store.approve(event_id, approved_by=req.approved_by)
    return {"event_id": event_id, "status": "approved"}


@app.get("/admin/events")
async def list_events() -> list[dict[str, str | None]]:
    """管理员查看统一运维事件。"""

    return [
        {
            "event_id": event.event_id,
            "event_type": str(event.event_type),
            "source": event.source,
            "user_id": event.user_id,
            "question": event.question,
            "device_id": event.device_id,
            "severity": event.severity,
            "status": event.status,
        }
        for event in reversed(list(store.events.values()))
    ]


@app.post("/forecast/run-once")
async def forecast_run_once(req: ForecastQueryRequest) -> dict[str, object]:
    """手动触发一次按需预测，并写入预测缓存。"""

    results = await app.state.forecast_agent.run_once(req, source="api", create_event=True)
    return {"count": len(results), "results": results}


@app.get("/forecast/cache")
async def forecast_cache() -> dict[str, object]:
    """查看预测缓存。"""

    return {"count": len(store.forecast_results), "items": list(store.forecast_results.values())}


@app.post("/security/check", response_model=SecurityDecision)
async def security_check(req: SecurityCheckRequest) -> SecurityDecision:
    """对变更指令做安全拦截/审批判断。"""

    return await app.state.security_guard_agent.assess(req)


@app.post("/remediation/plan/{event_id}", response_model=RemediationPlan)
async def remediation_plan(event_id: str) -> RemediationPlan:
    """基于诊断结果生成修复计划，不直接执行配置变更。"""

    diagnosis = store.diagnosis_results.get(event_id)
    if diagnosis is None:
        raise HTTPException(status_code=404, detail=f"未找到诊断结果：{event_id}")
    return await app.state.remediation_agent.build_plan(diagnosis)


@app.post("/remediation/close-loop/{event_id}", response_model=RemediationClosure)
async def remediation_close_loop(event_id: str) -> RemediationClosure:
    """场景 1 闭环预执行：生成控制命令并经过安全审查。

    当前不连接底层 SDN Controller，只返回可下发命令、需审批命令和阻断命令。
    """

    diagnosis = store.diagnosis_results.get(event_id)
    if diagnosis is None:
        raise HTTPException(status_code=404, detail=f"未找到诊断结果：{event_id}")
    return await app.state.remediation_agent.close_loop_preview(
        diagnosis=diagnosis,
        security_guard=app.state.security_guard_agent,
    )


@app.get("/remediation/close-loop/{event_id}", response_model=RemediationClosure)
async def remediation_close_loop_result(event_id: str) -> RemediationClosure:
    """查看最近一次场景 1 闭环预执行结果。"""

    closure = store.remediation_closures.get(event_id)
    if closure is None:
        raise HTTPException(status_code=404, detail=f"未找到闭环预执行结果：{event_id}")
    return closure


@app.get("/admin/audit-logs")
async def audit_logs() -> dict[str, object]:
    """查看安全护栏审计记录。"""

    return {"count": len(store.audit_logs), "items": list(store.audit_logs.values())}
