"""DiagnosisAgent: consume structured ops events and aggregate evidence."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import build_diagnosis_graph, build_ops_workflow_graph
from app.agents.remediation_agent import RemediationAgent
from app.agents.security_guard_agent import SecurityGuardAgent
from app.mcp_clients import netbox_client, prometheus_client
from app.mcp_clients.rag_client import search_knowledge_base
from app.mcp.client import get_standard_mcp_manager
from app.schemas import AnomalyEvent, DiagnosisResult, RemediationClosure, SecurityCheckRequest
from app.services.sdn_controller_adapter import SDNControllerAdapter
from app.stores import OpsMemoryStore


class DiagnosisAgent:
    """监听 anomaly_queue 并执行后台诊断。"""

    metrics = [
        "packet_loss",
        "bandwidth_in",
        "bandwidth_out",
        "ap_load",
        "cpu_load",
        "connections",
        "latency",
        "interface_errors",
    ]

    def __init__(
        self,
        anomaly_queue: asyncio.Queue[AnomalyEvent],
        diagnosis_queue: asyncio.Queue[DiagnosisResult],
        store: OpsMemoryStore | None = None,
    ) -> None:
        self.anomaly_queue = anomaly_queue
        self.diagnosis_queue = diagnosis_queue
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)
        self.graph = None
        self.ops_workflow_graph = None
        self.remediation_agent = RemediationAgent(store=store)
        self.security_guard_agent = SecurityGuardAgent(store=store)
        self.sdn_adapter = SDNControllerAdapter()

    async def _ensure_graph(self) -> None:
        """按需初始化 LangGraph 诊断图，图内 LLM 可调用动态 MCP tools。"""

        if self.graph is not None:
            return
        self.logger.info("Initializing LangGraph diagnosis graph with MCP tools ...")
        self.graph = await build_diagnosis_graph(progress_callback=self._progress)
        self.logger.info("LangGraph diagnosis graph initialized.")

    async def _ensure_ops_workflow_graph(self) -> None:
        """按需初始化宏观运维闭环图。"""

        if self.ops_workflow_graph is not None:
            return
        self.logger.info("Initializing LangGraph ops workflow graph ...")
        self.ops_workflow_graph = build_ops_workflow_graph(self)
        self.logger.info("LangGraph ops workflow graph initialized.")

    async def run(self) -> None:
        """持续消费事件并按 event_type 分流。"""

        while True:
            event = await self.anomaly_queue.get()
            self.logger.info("Consumed event event_id=%s event_type=%s", event.event_id, event.event_type)
            self._progress(event.event_id, "diagnosis_started", "DiagnosisAgent 已接收任务，开始诊断。")
            try:
                if event.source == "chat" and event.event_type in {
                    "user_network_status_query",
                    "user_fault_report",
                    "user_diagnosis_request",
                }:
                    result = await self.handle_user_langgraph_diagnosis(event)
                elif event.event_type == "user_network_status_query":
                    result = await self.handle_user_network_status_query(event)
                elif event.event_type == "user_fault_report":
                    result = await self.handle_user_fault_report(event)
                elif event.event_type == "user_diagnosis_request":
                    result = await self.handle_user_diagnosis_request(event)
                elif event.event_type == "prometheus_alert":
                    result = await self.handle_prometheus_alert(event)
                elif event.event_type in {"timesfm_forecast_anomaly", "traffic_hotspot_warning", "link_congestion_forecast"}:
                    result = await self.handle_forecast_anomaly(event)
                elif event.event_type == "scheduled_inspection_anomaly":
                    result = await self.handle_prometheus_alert(event)
                else:
                    result = self.build_unsupported_event_result(event, f"暂未支持的事件类型：{event.event_type}")
                result = await self._complete_diagnosis_closure(result)
                await self.diagnosis_queue.put(result)
                self.logger.info(
                    "Diagnosis result produced event_id=%s risk_level=%s summary=%s",
                    result.event_id,
                    result.risk_level,
                    result.summary,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("DiagnosisAgent failed event_id=%s", event.event_id)
                self._progress(event.event_id, "failed", f"诊断流程异常：{type(exc).__name__}", "failed")
                await self.diagnosis_queue.put(await self._complete_diagnosis_closure(self._error_result(event, exc)))
            finally:
                self.anomaly_queue.task_done()

    async def _complete_diagnosis_closure(self, result: DiagnosisResult) -> DiagnosisResult:
        """Run the macro ops workflow graph after diagnosis."""

        try:
            await self._ensure_ops_workflow_graph()
            output = await self.ops_workflow_graph.ainvoke(  # type: ignore[union-attr]
                {"diagnosis_result": result},
                config={"recursion_limit": 20},
            )
            return output.get("diagnosis_result", result)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("DiagnosisAgent remediation closure failed event_id=%s", result.event_id)
            result.evidence["remediation_error"] = f"{type(exc).__name__}: {exc}"
            result.final_reasoning = (
                f"{result.summary or result.final_reasoning}\n\n"
                "闭环处置：修复计划或安全审查生成失败，已保留诊断结果等待人工处理。"
            )
            result.summary = result.final_reasoning
            self._progress(result.event_id, "failed", "修复闭环生成失败，已转人工处理。", "failed")
            return result

    async def workflow_ingest(self, state: dict[str, Any]) -> dict[str, Any]:
        """宏观闭环图入口：判断是否需要进入修复闭环。"""

        result: DiagnosisResult = state["diagnosis_result"]
        requires_remediation = self._should_build_remediation(result)
        self._progress(
            result.event_id,
            "workflow_ingest",
            "宏观运维闭环图已接收诊断结果，正在判断是否需要修复编排。",
        )
        return {"requires_remediation": requires_remediation}

    async def workflow_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成修复计划和候选控制命令。"""

        result: DiagnosisResult = state["diagnosis_result"]
        self._progress(result.event_id, "remediation_planning", "正在生成修复计划和控制指令。")
        plan = await self.remediation_agent.build_plan(result)
        return {"remediation_plan": plan}

    async def workflow_review(self, state: dict[str, Any]) -> dict[str, Any]:
        """对候选控制命令执行安全审查并形成闭环预执行结果。"""

        result: DiagnosisResult = state["diagnosis_result"]
        plan = state["remediation_plan"]
        self._progress(result.event_id, "security_review", "正在进行高风险指令安全审查。")

        decisions = []
        dispatchable = []
        approval_required = []
        blocked = []
        for command in plan.control_commands:
            decision = await self.security_guard_agent.assess(
                SecurityCheckRequest(
                    user_id="system-remediation",
                    command=command.command,
                    target=command.target,
                )
            )
            decisions.append(decision)
            if decision.decision == "allow":
                dispatchable.append(command)
            elif decision.decision == "approve_required":
                approval_required.append(command)
            else:
                blocked.append(command)

        if blocked:
            dispatch_status = "blocked"
            plan.status = "blocked"
        elif approval_required:
            dispatch_status = "approval_required"
        elif dispatchable:
            dispatch_status = "ready_for_controller"
            plan.status = "approved"
        else:
            dispatch_status = "no_command"

        closure = RemediationClosure(
            event_id=result.event_id,
            plan=plan,
            security_decisions=decisions,
            dispatchable_commands=dispatchable,
            approval_required_commands=approval_required,
            blocked_commands=blocked,
            dispatch_status=dispatch_status,  # type: ignore[arg-type]
        )
        if self.store is not None:
            self.store.save_remediation_plan(plan)
            self.store.save_remediation_closure(closure)
        return {"remediation_plan": plan, "remediation_closure": closure}

    async def workflow_approval_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        """需要人工审批时暂停，审批后继续执行。"""

        result: DiagnosisResult = state["diagnosis_result"]
        closure = state["remediation_closure"]
        if closure.approval_required_commands:
            self._progress(
                result.event_id,
                "waiting_approval",
                "存在需要人工确认的控制指令，已暂停下发，等待用户确认。",
                "waiting_approval",
            )
            await self._wait_for_approval(result.event_id)
            decision = self.store.approval_decisions.get(result.event_id, {}) if self.store is not None else {}
            if decision.get("approved") is False:
                self._progress(
                    result.event_id,
                    "approval_rejected",
                    "用户已拒绝执行需审批命令，跳过自动修复执行，直接生成诊断报告。",
                )
                return {"approval_rejected": True}
            self._progress(result.event_id, "approval_received", "已收到确认，继续执行控制指令 dry-run。")
        else:
            self._progress(result.event_id, "approval_skipped", "未发现需人工审批的高风险指令。")
        return {"approval_rejected": False}

    async def workflow_dispatch(self, state: dict[str, Any]) -> dict[str, Any]:
        """执行通过审查的控制命令 dry-run。"""

        result: DiagnosisResult = state["diagnosis_result"]
        closure = state["remediation_closure"]
        self._progress(result.event_id, "sdn_compile", "正在通过 SDN Controller Adapter 编译控制命令。")
        execution_results = await self._execute_dispatchable_commands_with_adapter(closure)
        if closure.approval_required_commands:
            execution_results.extend(await self._execute_approved_commands_with_adapter(closure))
        self._progress(result.event_id, "sdn_dispatch", "SDN Controller Adapter 已完成 mock dry-run/模拟下发。")
        return {"execution_results": execution_results}

    async def workflow_merge(self, state: dict[str, Any]) -> dict[str, Any]:
        """合并诊断、修复计划、安全审查和执行证据。"""

        result: DiagnosisResult = state["diagnosis_result"]
        closure = state["remediation_closure"]
        execution_results = state.get("execution_results", [])
        self._progress(result.event_id, "merge", "正在合并诊断、修复计划和控制命令执行证据。")
        result.evidence["remediation_closure"] = closure.model_dump()
        result.evidence["execution_results"] = execution_results
        result.recommendations = self._merge_recommendations(result.recommendations, closure)
        return {"diagnosis_result": result}

    async def workflow_verify(self, state: dict[str, Any]) -> dict[str, Any]:
        """验证闭环处置结果。"""

        result: DiagnosisResult = state["diagnosis_result"]
        closure = state.get("remediation_closure")
        execution_results = state.get("execution_results", [])
        self._progress(result.event_id, "verification", "正在验证修复结果。")
        if closure is None:
            verification = {
                "status": "no_remediation_closure",
                "fixed": False,
                "risk_level": result.risk_level,
                "message": "未形成修复闭环结果，已转人工复核。",
            }
        else:
            verification = self._verify_closure(result, closure, execution_results)
            result.evidence["remediation_closure"] = closure.model_dump()
            result.evidence["execution_results"] = execution_results
        result.evidence["verification"] = verification
        return {"diagnosis_result": result, "verification": verification}

    async def workflow_escalate(self, state: dict[str, Any]) -> dict[str, Any]:
        """自动闭环无法继续时转人工复核。"""

        result: DiagnosisResult = state["diagnosis_result"]
        closure = state.get("remediation_closure")
        if state.get("approval_rejected"):
            self._progress(
                result.event_id,
                "escalate",
                "用户拒绝执行修复命令，已跳过自动修复，仅生成诊断报告。",
            )
            result.evidence["approval_rejected"] = True
        else:
            self._progress(result.event_id, "escalate", "当前闭环无法自动执行，已转人工复核。")
        if closure is not None:
            result.evidence["remediation_closure"] = closure.model_dump()
            result.recommendations = self._merge_recommendations(result.recommendations, closure)
        return {"diagnosis_result": result, "execution_results": []}

    async def workflow_final_report(self, state: dict[str, Any]) -> dict[str, Any]:
        """生成最终诊断与闭环报告。"""

        result: DiagnosisResult = state["diagnosis_result"]
        if not state.get("requires_remediation"):
            self._progress(result.event_id, "completed", "无需进入自动修复闭环，诊断已完成。", "completed")
            if self.store is not None:
                self.store.save_diagnosis(result)
            return {"diagnosis_result": result}

        closure = state.get("remediation_closure")
        execution_results = state.get("execution_results", [])
        verification = state.get("verification", {})
        if closure is None:
            result.final_reasoning = (
                f"{result.summary or result.final_reasoning}\n\n"
                "闭环处置：未生成可执行修复闭环，已转人工复核。"
            )
        else:
            result.final_reasoning = self._build_closed_loop_report(result, closure, execution_results, verification)
        result.summary = result.final_reasoning
        self._progress(result.event_id, "completed", "最终诊断与修复闭环报告已生成。", "completed")
        if self.store is not None:
            self.store.save_diagnosis(result)
        return {"diagnosis_result": result}

    def _progress(self, event_id: str, stage: str, message: str, status: str = "running") -> None:
        if self.store is not None:
            self.store.add_progress(event_id, stage, message, status)

    async def _wait_for_approval(self, event_id: str) -> None:
        if self.store is None:
            return
        await self.store.approval_event(event_id).wait()

    @staticmethod
    def _should_build_remediation(result: DiagnosisResult) -> bool:
        if result.risk_level in {"warning", "critical"}:
            return True
        if result.source in {"telemetry", "prometheus", "forecast"}:
            return True
        if result.event_type in {
            "user_fault_report",
            "user_diagnosis_request",
            "prometheus_alert",
            "timesfm_forecast_anomaly",
            "traffic_hotspot_warning",
            "link_congestion_forecast",
            "device_down",
            "interface_down",
            "packet_loss_anomaly",
            "ap_overload",
        }:
            return True
        return False

    @staticmethod
    def _mock_execute_dispatchable_commands(closure: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for command in closure.dispatchable_commands:
            results.append(
                {
                    "command_id": command.command_id,
                    "command_type": command.command_type,
                    "target": command.target,
                    "command": command.command,
                    "dry_run": True,
                    "status": "validated_not_dispatched",
                    "success": True,
                    "executor": "DiagnosisAgent.mock_executor",
                    "message": "命令通过安全审查并完成 dry-run 校验；当前未连接 SDN Controller，未真实下发。",
                }
            )
        return results

    async def _execute_dispatchable_commands_with_adapter(self, closure: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for command in closure.dispatchable_commands:
            self._progress(
                closure.event_id,
                "sdn_command_dry_run",
                f"正在对低风险命令进行 SDN Adapter dry-run：{command.command}",
            )
            result = await self.sdn_adapter.dry_run(command)
            results.append(result.model_dump())
        return results

    @staticmethod
    def _mock_execute_approved_commands(closure: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for command in closure.approval_required_commands:
            results.append(
                {
                    "command_id": command.command_id,
                    "command_type": command.command_type,
                    "target": command.target,
                    "command": command.command,
                    "dry_run": True,
                    "status": "approved_validated_not_dispatched",
                    "success": True,
                    "executor": "DiagnosisAgent.mock_sdn_controller",
                    "message": "用户已确认；命令完成 mock SDN dry-run 校验，当前未真实下发到底层控制器。",
                }
            )
        return results

    async def _execute_approved_commands_with_adapter(self, closure: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for command in closure.approval_required_commands:
            self._progress(
                closure.event_id,
                "sdn_command_dispatch",
                f"正在对已审批命令执行 SDN Adapter mock 下发：{command.command}",
            )
            result = await self.sdn_adapter.dispatch(command, approved=True)
            results.append(result.model_dump())
        return results

    @staticmethod
    def _verify_closure(
        result: DiagnosisResult,
        closure: Any,
        execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if closure.blocked_commands:
            status = "blocked"
            fixed = False
            message = "存在被安全护栏阻断的命令，问题未进入自动修复执行阶段。"
        elif closure.approval_required_commands:
            if result.evidence.get("approval_rejected"):
                status = "approval_rejected"
                fixed = False
                message = "用户拒绝执行需审批命令，自动修复已跳过；本次仅输出诊断结论和人工处置建议。"
            else:
                status = "approved_dry_run_validated"
                fixed = False
                message = "需审批命令已在用户确认后完成 dry-run 校验；当前未连接真实 SDN Controller，问题不能判定已解决。"
        elif execution_results:
            status = "dry_run_validated"
            fixed = False
            message = "低风险命令已完成 dry-run 校验，但未连接 SDN Controller，不能判定网络状态已恢复。"
        else:
            status = "no_executable_command"
            fixed = False
            message = "未生成可自动处理命令，需要人工复核。"
        return {
            "status": status,
            "fixed": fixed,
            "risk_level": result.risk_level,
            "message": message,
        }

    @staticmethod
    def _merge_recommendations(recommendations: list[str], closure: Any) -> list[str]:
        merged = list(recommendations)
        if closure.dispatchable_commands:
            merged.append("低风险只读/探测命令已通过安全审查，可接入控制器后自动下发。")
        if closure.approval_required_commands:
            merged.append("存在中高风险控制命令，需要管理员审批后才能执行。")
        if closure.blocked_commands:
            merged.append("存在被安全策略阻断的命令，应转人工安全复核。")
        return list(dict.fromkeys(merged))

    @staticmethod
    def _build_closed_loop_report(
        result: DiagnosisResult,
        closure: Any,
        execution_results: list[dict[str, Any]],
        verification: dict[str, Any],
    ) -> str:
        question = result.question or result.issue_desc or "未提供"
        diagnosis_text = result.final_reasoning or result.summary or "暂无诊断结论。"
        dispatchable = DiagnosisAgent._format_commands(closure.dispatchable_commands)
        approval_required = DiagnosisAgent._format_commands(closure.approval_required_commands)
        blocked = DiagnosisAgent._format_commands(closure.blocked_commands)
        execution_text = DiagnosisAgent._format_execution_results(execution_results)
        security_text = "\n".join(
            f"{index}. {decision.decision} / {decision.risk_level}：{decision.reason}"
            for index, decision in enumerate(closure.security_decisions, start=1)
        ) or "无安全审查记录。"
        final_status = "已解决" if verification.get("fixed") else "未完全解决"
        return (
            f"任务 ID：{result.event_id}\n\n"
            f"用户问题：\n{question}\n\n"
            f"最终状态：\n{final_status}（{verification.get('status')}）\n\n"
            f"诊断结论：\n{diagnosis_text}\n\n"
            f"风险等级：\n{result.risk_level}\n\n"
            f"修复计划：\n{DiagnosisAgent._format_plain_list(closure.plan.actions)}\n\n"
            f"可直接执行的控制命令：\n{dispatchable}\n\n"
            f"需要人工审批的控制命令：\n{approval_required}\n\n"
            f"被阻断的控制命令：\n{blocked}\n\n"
            f"安全审查结果：\n{security_text}\n\n"
            f"执行结果：\n{execution_text}\n\n"
            f"验证结果：\n{verification.get('message')}\n\n"
            "说明：当前版本由 DiagnosisAgent 完成诊断、修复计划、安全审查和 dry-run 预执行编排；"
            "尚未真实连接 SDN Controller，因此不会声称问题已经自动修复。"
        )

    @staticmethod
    def _format_commands(commands: list[Any]) -> str:
        if not commands:
            return "无。"
        return "\n".join(
            f"{index}. [{command.command_type}] {command.command}；目标：{command.target}；原因：{command.rationale}"
            for index, command in enumerate(commands, start=1)
        )

    @staticmethod
    def _format_execution_results(results: list[dict[str, Any]]) -> str:
        if not results:
            return "无命令执行。"
        return "\n".join(
            f"{index}. {item.get('command')} -> {item.get('status')}；{item.get('message')}"
            for index, item in enumerate(results, start=1)
        )

    @staticmethod
    def _format_plain_list(items: list[str]) -> str:
        if not items:
            return "无。"
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))

    async def handle_user_langgraph_diagnosis(self, event: AnomalyEvent) -> DiagnosisResult:
        """用户触发事件走 LangGraph：LLM 自主选择并调用 MCP tools。"""

        await self._ensure_graph()
        prompt = self._build_langgraph_prompt(event)
        graph_input: dict[str, Any] = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "location": self._location(event),
            "issue_desc": event.issue_desc or event.question or "",
            "messages": [HumanMessage(content=prompt)],
        }
        output = await asyncio.wait_for(
            self.graph.ainvoke(  # type: ignore[union-attr]
                graph_input,
                config={"recursion_limit": 30},
            ),
            timeout=120,
        )
        messages = output.get("messages", [])
        final_reasoning = self._extract_final_reasoning(messages)
        tool_trace = self._extract_langgraph_tool_trace(messages)
        missing_evidence = self._missing_from_langgraph_trace(tool_trace)
        risk_level = self._risk_from_text(final_reasoning)
        return DiagnosisResult(
            event_id=event.event_id,
            event_type=str(event.event_type),
            source=event.source,
            question=event.question,
            location=self._location(event),
            issue_desc=event.issue_desc or event.question or "",
            summary=final_reasoning,
            risk_level=risk_level,  # type: ignore[arg-type]
            evidence={
                "topology": {},
                "metrics": {},
                "knowledge": [],
                "tool_calls": tool_trace,
                "langgraph_messages_count": len(messages),
            },
            possible_causes=[],
            recommendations=[],
            missing_evidence=missing_evidence,
            suspect_devices=[event.device_id or event.device_hint] if (event.device_id or event.device_hint) else [],
            final_reasoning=final_reasoning,
        )

    def _build_langgraph_prompt(self, event: AnomalyEvent) -> str:
        return (
            "你是 CampusNet-Copilot 的高级校园网诊断 Agent。"
            "本次必须通过可用工具获取证据后再判断实时网络状态，不能编造设备状态或指标。\n\n"
            f"事件ID: {event.event_id}\n"
            f"事件类型: {event.event_type}\n"
            f"来源: {event.source}\n"
            f"用户ID: {event.user_id or 'unknown'}\n"
            f"地点线索: {event.location_hint or event.location or '未提供'}\n"
            f"设备线索: {event.device_id or event.device_hint or '未提供'}\n"
            f"指标线索: {event.metric or '未提供'}\n"
            f"故障现象: {event.symptom or event.issue_desc or '未提供'}\n"
            f"用户原问题: {event.question or event.issue_desc}\n\n"
            "请按以下策略执行：\n"
            "1. 优先调用 NetBox MCP 查询相关位置、设备、接口、拓扑或影响范围。\n"
            "2. 调用 Prometheus MCP 查询当前和最近 5 到 30 分钟指标，至少关注 packet_loss、latency、cpu_load、connections；如工具支持，也查询 AP 负载、带宽、接口错误。\n"
            "   重要：Prometheus 的 device_id 标签必须使用 NetBox 设备 name，例如 AP-LIB-3F-02 或 SW-LIB-AGG-01；"
            "不要使用 NetBox 内部数字 id，例如 1、2、3，否则会查不到设备指标。\n"
            "   如果 NetBox 返回设备对象，先提取 name 字段，再把这些 name 作为 get_device_metrics 的 device_ids。\n"
            "3. 如果用户问题包含明天、后天、今晚、未来、预测、预计、会不会等未来时间或预测意图，"
            "必须先用 Prometheus MCP 获取相关设备当前/历史指标，再调用 TimesFM MCP 的 forecast_metric、"
            "forecast_quantile 或 detect_anomaly_window 预测未来 packet_loss、cpu_load、connections 等指标；"
            "明天可按 horizon_minutes=1440、freq='30m' 或工具可承受的相近窗口执行。"
            "最终回答要明确区分“当前观测值”和“未来预测值/风险”。\n"
            "4. 可调用知识库/RAG 或可用的运维经验工具补充常见原因。\n"
            "5. 最终输出中文诊断结果，必须包含：诊断摘要、风险等级、关键证据、可能原因、建议操作、缺失证据。\n"
            "6. 如果某类工具证据不可用，请明确写明，不要用猜测替代。"
        )

    @staticmethod
    def _extract_final_reasoning(messages: list[Any]) -> str:
        for msg in reversed(messages):
            if not isinstance(msg, AIMessage):
                continue
            content = msg.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                joined = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                ).strip()
                if joined:
                    return joined
        return "暂无结论"

    @staticmethod
    def _extract_langgraph_tool_trace(messages: list[Any]) -> list[dict[str, str]]:
        traces: list[dict[str, str]] = [
            {
                "component": "LLM",
                "tool": "LangGraph.call_model",
                "status": "ok",
                "detail": "DiagnosisAgent 内 LLM 已参与推理，并可根据需要发起 MCP 工具调用。",
            }
        ]
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for call in msg.tool_calls:
                    name = str(call.get("name", "unknown"))
                    traces.append(
                        {
                            "component": DiagnosisAgent._component_from_tool_name(name),
                            "tool": name,
                            "status": "requested",
                            "detail": str(call.get("args", {})),
                        }
                    )
            elif isinstance(msg, ToolMessage):
                name = str(getattr(msg, "name", None) or "unknown")
                content = getattr(msg, "content", "")
                ok = '"ok": false' not in str(content).lower()
                traces.append(
                    {
                        "component": DiagnosisAgent._component_from_tool_name(name),
                        "tool": name,
                        "status": "ok" if ok else "failed",
                        "detail": str(content)[:300],
                    }
                )
        return traces

    @staticmethod
    def _component_from_tool_name(tool_name: str) -> str:
        lowered = tool_name.lower()
        if "netbox" in lowered:
            return "NetBox MCP"
        if "prometheus" in lowered or "metric" in lowered or "query" in lowered:
            return "Prometheus MCP"
        if "rag" in lowered or "knowledge" in lowered:
            return "RAG"
        return "MCP Tool"

    @staticmethod
    def _missing_from_langgraph_trace(tool_trace: list[dict[str, str]]) -> list[str]:
        text = " ".join(f"{item.get('component')} {item.get('tool')} {item.get('status')}" for item in tool_trace)
        missing: list[str] = []
        if "NetBox MCP" not in text:
            missing.append("topology")
        if "Prometheus MCP" not in text:
            missing.append("metrics")
        return missing

    @staticmethod
    def _risk_from_text(text: str) -> str:
        if any(word in text for word in ["critical", "严重", "高风险", "中断"]):
            return "critical"
        if any(word in text for word in ["warning", "告警", "风险", "偏高", "异常", "丢包"]):
            return "warning"
        if any(word in text for word in ["normal", "正常", "未发现明显异常"]):
            return "normal"
        return "unknown"

    async def handle_user_network_status_query(self, event: AnomalyEvent) -> DiagnosisResult:
        location = self._location(event)
        topology, metrics, missing = await self._collect_topology_and_metrics(event, location)
        trusted_metrics = self._trusted_metrics(metrics)
        risk_level = self._risk_from_metrics(trusted_metrics)
        summary = self._status_summary(location, risk_level)
        return self._result(
            event,
            summary=summary,
            risk_level=risk_level,
            evidence={"topology": topology, "metrics": metrics, "knowledge": [], "tool_calls": self._tool_calls(topology, metrics, [])},
            possible_causes=self._causes_for_metrics(trusted_metrics),
            recommendations=self._recommendations_for_risk(risk_level),
            missing_evidence=missing,
        )

    async def handle_user_fault_report(self, event: AnomalyEvent) -> DiagnosisResult:
        location = self._location(event)
        topology, metrics, missing = await self._collect_topology_and_metrics(event, location)
        knowledge, knowledge_missing = await self._collect_knowledge(event)
        missing.extend(knowledge_missing)
        trusted_metrics = self._trusted_metrics(metrics)
        risk_level = self._risk_from_metrics(trusted_metrics)
        causes = self._causes_for_metrics(trusted_metrics)
        summary = (
            f"{location or '相关区域'}故障现象更可能与{causes[0]}有关。"
            if causes
            else f"{location or '相关区域'}需要真实拓扑和实时指标后才能判断故障原因。"
        )
        return self._result(
            event,
            summary=summary,
            risk_level=risk_level,
            evidence={"topology": topology, "metrics": metrics, "knowledge": knowledge, "tool_calls": self._tool_calls(topology, metrics, knowledge)},
            possible_causes=causes,
            recommendations=self._recommendations_for_risk(risk_level),
            missing_evidence=missing,
        )

    async def handle_user_diagnosis_request(self, event: AnomalyEvent) -> DiagnosisResult:
        location = self._location(event)
        topology, metrics, missing = await self._collect_topology_and_metrics(event, location)
        knowledge, knowledge_missing = await self._collect_knowledge(event)
        missing.extend(knowledge_missing)
        trusted_metrics = self._trusted_metrics(metrics)
        risk_level = self._risk_from_metrics(trusted_metrics)
        causes = self._causes_for_metrics(trusted_metrics)
        hypothesis = "出口链路问题" if "出口" in (event.question or event.issue_desc) else "用户提出的故障假设"
        supported = any(
            values.get("bandwidth_out", {}).get("value", 0) and values["bandwidth_out"]["value"] >= 90
            for values in trusted_metrics.values()
        )
        summary = (f"现有证据{'支持' if supported else '暂不支持'}“{hypothesis}”。"
            f"更需要关注：{causes[0]}。"
            if trusted_metrics
            else f"暂未获得足够真实指标证据，无法判断“{hypothesis}”是否成立。"
        )
        return self._result(
            event,
            summary=summary,
            risk_level=risk_level,
            evidence={"topology": topology, "metrics": metrics, "knowledge": knowledge, "tool_calls": self._tool_calls(topology, metrics, knowledge)},
            possible_causes=causes,
            recommendations=self._recommendations_for_risk(risk_level),
            missing_evidence=missing,
        )

    async def handle_prometheus_alert(self, event: AnomalyEvent) -> DiagnosisResult:
        location = self._location(event)
        topology, metrics, missing = await self._collect_topology_and_metrics(event, location)
        if event.packet_loss > 0 or event.latency_ms > 0:
            metrics.setdefault(event.device_hint or "telemetry", {})["telemetry_snapshot"] = {
                "packet_loss": event.packet_loss,
                "latency_ms": event.latency_ms,
            }
        risk_level = "critical" if event.packet_loss >= 0.08 or event.latency_ms >= 200 else "warning"
        summary = f"{location or '未知区域'}检测到遥测异常，建议结合拓扑和实时指标继续排查。"
        return self._result(
            event,
            summary=summary,
            risk_level=risk_level,
            evidence={"topology": topology, "metrics": metrics, "knowledge": [], "tool_calls": self._tool_calls(topology, metrics, [])},
            possible_causes=self._causes_for_metrics(self._trusted_metrics(metrics)) or ["链路丢包或高延迟"],
            recommendations=self._recommendations_for_risk(risk_level),
            missing_evidence=missing,
        )

    async def handle_forecast_anomaly(self, event: AnomalyEvent) -> DiagnosisResult:
        forecast = event.metadata.get("forecast", {}) if isinstance(event.metadata, dict) else {}
        device_id = event.device_id or str(forecast.get("device_id", ""))
        metric = event.metric or str(forecast.get("metric", ""))
        risk_level = str(forecast.get("risk_level") or event.severity or "warning")
        if risk_level not in {"normal", "warning", "critical", "unknown"}:
            risk_level = "warning"
        summary = (
            f"预测模型发现 {device_id or '相关设备'} 的 {metric or '关键指标'} "
            f"在未来窗口存在 {risk_level} 级风险。"
        )
        recommendations = [
            "结合当前 Prometheus 指标确认风险是否已经出现",
            "提前检查热点区域容量、AP 连接数和上联链路利用率",
            "必要时准备负载均衡、终端分流或临时扩容方案",
        ]
        return self._result(
            event,
            summary=summary,
            risk_level=risk_level,
            evidence={"topology": {}, "metrics": {}, "knowledge": [], "forecast": forecast, "tool_calls": []},
            possible_causes=[f"{device_id or '相关设备'} 的 {metric or '关键指标'} 预测值接近或超过阈值"],
            recommendations=recommendations,
            missing_evidence=[] if forecast else ["metrics"],
        )

    def build_unsupported_event_result(self, event: AnomalyEvent, message: str) -> DiagnosisResult:
        self.logger.warning("Unsupported event event_id=%s event_type=%s", event.event_id, event.event_type)
        return self._result(
            event,
            summary=message,
            risk_level="unknown",
            evidence={"topology": {}, "metrics": {}, "knowledge": [], "tool_calls": self._tool_calls({}, {}, [])},
            possible_causes=[],
            recommendations=["等待后续版本支持该事件类型，或转为人工排查。"],
            missing_evidence=["topology", "metrics", "knowledge"],
        )

    async def _collect_topology_and_metrics(
        self,
        event: AnomalyEvent,
        location: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        missing: list[str] = []
        topology: dict[str, Any] = {}
        metrics: dict[str, Any] = {}

        try:
            devices = (
                [await netbox_client.get_device_detail(event.device_id)]
                if event.device_id
                else await netbox_client.get_devices_by_location(location)
            )
            topology["devices"] = devices
            topology["links"] = {}
            topology["affected_scope"] = {}
            for device in devices:
                device_id = str(device.get("device_id", ""))
                if not device_id:
                    continue
                topology["links"][device_id] = await netbox_client.get_device_links(device_id)
                topology["affected_scope"][device_id] = await netbox_client.get_affected_scope(device_id)
        except Exception:  # noqa: BLE001
            self.logger.exception("NetBox evidence failed event_id=%s", event.event_id)
            missing.append("topology")
            devices = []

        try:
            for device in devices:
                device_id = str(device.get("device_id", ""))
                if not device_id:
                    continue
                metric_values = await asyncio.gather(
                    *(prometheus_client.get_metric_avg(device_id, metric, "5m") for metric in self.metrics)
                )
                metrics[device_id] = {item["metric"]: item for item in metric_values}
        except Exception:  # noqa: BLE001
            self.logger.exception("Prometheus evidence failed event_id=%s", event.event_id)
            missing.append("metrics")

        self.logger.info(
            "Tool evidence event_id=%s netbox_ok=%s prometheus_ok=%s",
            event.event_id,
            "topology" not in missing,
            "metrics" not in missing,
        )
        if not topology.get("devices") or any(
            device.get("source") == "mock_fallback" for device in topology.get("devices", [])
        ):
            missing.append("topology")
        if not metrics or any(
            isinstance(metric_payload, dict) and metric_payload.get("source") == "mock_fallback"
            for device_metrics in metrics.values()
            for metric_payload in device_metrics.values()
        ) or all(
            isinstance(metric_payload, dict) and metric_payload.get("value") is None
            for device_metrics in metrics.values()
            for metric_payload in device_metrics.values()
        ):
            missing.append("metrics")
        return topology, metrics, missing

    async def _collect_knowledge(self, event: AnomalyEvent) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            chunks = await search_knowledge_base(event.question or event.issue_desc, top_k=3)
            return [
                {"title": chunk.title, "content": chunk.content, "score": chunk.score, "source": chunk.source}
                for chunk in chunks
            ], []
        except Exception:  # noqa: BLE001
            self.logger.exception("RAG evidence failed event_id=%s", event.event_id)
            return [], ["knowledge"]

    def _result(
        self,
        event: AnomalyEvent,
        summary: str,
        risk_level: str,
        evidence: dict[str, Any],
        possible_causes: list[str],
        recommendations: list[str],
        missing_evidence: list[str],
    ) -> DiagnosisResult:
        final_reasoning = summary
        location = self._location(event)
        return DiagnosisResult(
            event_id=event.event_id,
            event_type=str(event.event_type),
            source=event.source,
            question=event.question,
            location=location,
            issue_desc=event.issue_desc or event.question or "",
            summary=summary,
            risk_level=risk_level,  # type: ignore[arg-type]
            evidence=evidence,
            possible_causes=possible_causes,
            recommendations=recommendations,
            missing_evidence=list(dict.fromkeys(missing_evidence)),
            suspect_devices=self._suspect_devices(evidence),
            final_reasoning=final_reasoning,
        )

    def _error_result(self, event: AnomalyEvent, exc: Exception) -> DiagnosisResult:
        return self._result(
            event,
            summary=f"诊断流程异常：{type(exc).__name__}: {exc}",
            risk_level="unknown",
            evidence={"topology": {}, "metrics": {}, "knowledge": []},
            possible_causes=[],
            recommendations=["请稍后重试，或由运维人员查看后台日志。"],
            missing_evidence=["topology", "metrics", "knowledge"],
        )

    @staticmethod
    def _location(event: AnomalyEvent) -> str:
        return event.location_hint or event.location or ""

    @staticmethod
    def _suspect_devices(evidence: dict[str, Any]) -> list[str]:
        metrics = DiagnosisAgent._trusted_metrics(evidence.get("metrics", {}))
        suspects: list[str] = []
        for device_id, values in metrics.items():
            if values.get("ap_load", {}).get("value", 0) >= 85 or values.get("packet_loss", {}).get("value", 0) >= 0.03:
                suspects.append(device_id)
        return suspects

    @staticmethod
    def _tool_calls(
        topology: dict[str, Any],
        metrics: dict[str, Any],
        knowledge: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        devices = topology.get("devices", [])
        topology_sources = {
            str(device.get("source", "unknown"))
            for device in devices
            if isinstance(device, dict)
        }
        metric_sources = {
            str(payload.get("source", "unknown"))
            for values in metrics.values()
            if isinstance(values, dict)
            for payload in values.values()
            if isinstance(payload, dict)
        }
        return [
            {
                "component": "ChatRouter",
                "tool": "rule_based_classify",
                "status": "ok",
                "detail": "规则分类；未调用 LLM。",
            },
            {
                "component": "NetBox MCP",
                "tool": "netbox_get_objects",
                "status": DiagnosisAgent._source_status(topology_sources, "netbox_mcp"),
                "detail": DiagnosisAgent._source_detail(topology_sources),
            },
            {
                "component": "Prometheus MCP",
                "tool": "get_device_metrics / instant_query",
                "status": DiagnosisAgent._source_status(metric_sources, "prometheus_mcp"),
                "detail": DiagnosisAgent._source_detail(metric_sources),
            },
            {
                "component": "RAG",
                "tool": "search_knowledge_base",
                "status": "ok" if knowledge else "not_called_or_empty",
                "detail": "当前为本地知识库/mock RAG；非 NetBox/Prometheus 实时查询。",
            },
            {
                "component": "LLM",
                "tool": "none",
                "status": "not_called",
                "detail": "当前诊断摘要和报告由规则模板基于工具证据生成，未调用模型生成结论。",
            },
        ]

    @staticmethod
    def _source_status(sources: set[str], expected_prefix: str) -> str:
        if not sources:
            return "not_called_or_empty"
        if any(source.startswith(expected_prefix) for source in sources):
            return "ok" if all(source.startswith(expected_prefix) for source in sources) else "partial"
        if "mock_fallback" in sources:
            return "fallback"
        return "unknown"

    @staticmethod
    def _source_detail(sources: set[str]) -> str:
        return ", ".join(sorted(sources)) if sources else "no evidence returned"

    @staticmethod
    def _trusted_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        trusted: dict[str, Any] = {}
        for device_id, values in metrics.items():
            if not isinstance(values, dict):
                continue
            filtered = {
                metric_name: payload
                for metric_name, payload in values.items()
                if not isinstance(payload, dict) or payload.get("source") != "mock_fallback"
            }
            if filtered:
                trusted[device_id] = filtered
        return trusted

    @staticmethod
    def _risk_from_metrics(metrics: dict[str, Any]) -> str:
        if not metrics:
            return "unknown"
        risk = "normal"
        for values in metrics.values():
            packet_loss = values.get("packet_loss", {}).get("value") or 0
            ap_load = values.get("ap_load", {}).get("value") or 0
            bandwidth_out = values.get("bandwidth_out", {}).get("value") or 0
            latency = values.get("latency", {}).get("value") or 0
            if packet_loss >= 0.05 or ap_load >= 92 or bandwidth_out >= 95 or latency >= 120:
                return "critical"
            if packet_loss >= 0.02 or ap_load >= 85 or bandwidth_out >= 85 or latency >= 50:
                risk = "warning"
        return risk

    @staticmethod
    def _causes_for_metrics(metrics: dict[str, Any]) -> list[str]:
        if not metrics:
            return []
        causes: list[str] = []
        for device_id, values in metrics.items():
            if values.get("ap_load", {}).get("value", 0) >= 85:
                causes.append(f"{device_id} AP 负载偏高")
            if values.get("bandwidth_out", {}).get("value", 0) >= 85:
                causes.append(f"{device_id} 上联带宽利用率偏高")
            if values.get("packet_loss", {}).get("value", 0) >= 0.02:
                causes.append(f"{device_id} 丢包率升高")
            if values.get("interface_errors", {}).get("value", 0) > 0:
                causes.append(f"{device_id} 接口错误包需要关注")
        return causes or ["未发现明确异常指标，可能需要补充更细粒度现场证据"]

    @staticmethod
    def _recommendations_for_risk(risk_level: str) -> list[str]:
        if risk_level == "critical":
            return ["优先检查高负载 AP 和上联链路", "查看是否存在异常大流量终端", "必要时进行流量疏导或临时扩容"]
        if risk_level == "warning":
            return ["持续观察最近 30 分钟趋势", "核查 AP 在线终端数和信道干扰", "检查上联口错误包和带宽利用率"]
        if risk_level == "normal":
            return ["当前未发现明显异常，可继续观察", "如用户仍感知卡顿，建议补充终端、时间段和具体业务信息"]
        return ["补充拓扑、实时指标和现场现象后再判断"]

    @staticmethod
    def _status_summary(location: str, risk_level: str) -> str:
        if risk_level == "normal":
            return f"{location or '相关区域'}当前网络状态整体正常，暂未发现明显异常指标。"
        if risk_level == "warning":
            return f"{location or '相关区域'}当前存在轻度风险，部分设备指标接近阈值。"
        if risk_level == "critical":
            return f"{location or '相关区域'}当前存在较高风险，已有关键指标超过阈值。"
        return f"{location or '相关区域'}当前状态未知，需要补充工具证据。"
