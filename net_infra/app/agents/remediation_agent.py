"""RemediationAgent: propose repair plans without executing risky changes."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from app.schemas import ControlCommand, DiagnosisResult, RemediationClosure, RemediationPlan, SecurityCheckRequest
from app.stores import OpsMemoryStore

if TYPE_CHECKING:
    from app.agents.security_guard_agent import SecurityGuardAgent


class RemediationAgent:
    """Generate controlled repair plans from diagnosis results."""

    def __init__(self, store: OpsMemoryStore | None = None) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    async def build_plan(self, diagnosis: DiagnosisResult) -> RemediationPlan:
        actions = self._actions_for_diagnosis(diagnosis)
        control_commands = self._commands_for_diagnosis(diagnosis)
        requires_approval = any(command.requires_approval for command in control_commands) or diagnosis.risk_level in {
            "warning",
            "critical",
        }
        action_type = "approval_required" if requires_approval else "low_risk_auto_check"
        plan = RemediationPlan(
            event_id=diagnosis.event_id,
            risk_level=diagnosis.risk_level,
            action_type=action_type,
            actions=actions,
            control_commands=control_commands,
            requires_approval=requires_approval,
            status="proposed",
            reason="基于诊断结果生成修复计划。本阶段只确定待下发控制命令，不直接调用 SDN Controller。",
        )
        if self.store is not None:
            self.store.save_remediation_plan(plan)
        self.logger.info("Remediation plan generated event_id=%s plan_id=%s", diagnosis.event_id, plan.plan_id)
        return plan

    async def close_loop_preview(
        self,
        diagnosis: DiagnosisResult,
        security_guard: "SecurityGuardAgent",
    ) -> RemediationClosure:
        """Generate commands and run security checks without dispatching to SDN."""

        plan = await self.build_plan(diagnosis)
        decisions = []
        dispatchable: list[ControlCommand] = []
        approval_required: list[ControlCommand] = []
        blocked: list[ControlCommand] = []

        for command in plan.control_commands:
            decision = await security_guard.assess(
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
            event_id=diagnosis.event_id,
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
        self.logger.info(
            "Remediation close-loop preview event_id=%s status=%s dispatchable=%d approval=%d blocked=%d",
            diagnosis.event_id,
            closure.dispatch_status,
            len(dispatchable),
            len(approval_required),
            len(blocked),
        )
        return closure

    @staticmethod
    def _actions_for_diagnosis(diagnosis: DiagnosisResult) -> list[str]:
        text = " ".join([diagnosis.summary, *diagnosis.possible_causes]).lower()
        actions: list[str] = []
        if "ap" in text or "无线" in text or "wifi" in text:
            actions.extend([
                "检查 AP 在线终端数、信道利用率和干扰情况",
                "确认相邻 AP 信道规划，必要时调整信道或进行终端分流",
            ])
        if "丢包" in text or "packet_loss" in text:
            actions.extend([
                "检查相关设备上联口错误包、丢包和光模块状态",
                "对异常链路执行连通性测试，确认是否需要切换备用链路",
            ])
        if "带宽" in text or "拥塞" in text or "connections" in text:
            actions.extend([
                "查看热点区域大流量终端或业务，必要时限速或疏导",
                "评估临时扩容或负载均衡策略",
            ])
        if not actions:
            actions.append("补充拓扑、实时指标和现场现象后由运维人员复核")
        return list(dict.fromkeys(actions))

    def _commands_for_diagnosis(self, diagnosis: DiagnosisResult) -> list[ControlCommand]:
        devices = self._target_devices(diagnosis)
        text = " ".join([diagnosis.summary, *diagnosis.possible_causes, *diagnosis.recommendations]).lower()
        commands: list[ControlCommand] = []

        for device in devices:
            commands.append(
                ControlCommand(
                    command_type="collect_runtime_snapshot",
                    target=device,
                    command=f"collect_runtime_snapshot --device {device} --metrics packet_loss,latency,cpu_load,connections,interface_errors",
                    risk_level="normal",
                    requires_approval=False,
                    rationale="低风险只读动作：重新采集当前运行指标，作为修复前基线。",
                )
            )
            commands.append(
                ControlCommand(
                    command_type="run_connectivity_probe",
                    target=device,
                    command=f"run_connectivity_probe --target {device} --count 20 --timeout-ms 1000",
                    risk_level="normal",
                    requires_approval=False,
                    rationale="低风险只读动作：确认设备和链路连通性。",
                )
            )

        if "ap" in text or "wifi" in text or "无线" in text:
            for device in devices:
                if "AP-" not in device.upper():
                    continue
                commands.append(
                    ControlCommand(
                        command_type="ap_client_audit",
                        target=device,
                        command=f"ap_client_audit --ap {device} --top-talkers 10 --include-rssi",
                        risk_level="normal",
                        requires_approval=False,
                        rationale="低风险只读动作：定位高占用终端、弱信号重传和连接数压力。",
                    )
                )
                commands.append(
                    ControlCommand(
                        command_type="ap_channel_rebalance",
                        target=device,
                        command=f"ap_channel_rebalance --ap {device} --mode suggest-only",
                        risk_level="warning",
                        requires_approval=True,
                        rationale="中风险动作：调整信道会影响无线覆盖，当前只生成建议命令，需审批后下发。",
                    )
                )
                if any(keyword in text for keyword in ["过载", "负载", "并发连接", "client balancing", "band steering"]):
                    commands.append(
                        ControlCommand(
                            command_type="ap_client_balance",
                            target=device,
                            command=f"ap_client_balance --ap {device} --mode suggest-only",
                            risk_level="warning",
                            requires_approval=True,
                            rationale="中风险动作：客户端负载均衡可能改变终端接入 AP，需审批后下发。",
                        )
                    )

        if any(keyword in text for keyword in ["宕机", "不可达", "监控脱管", "无数据", "poe", "电源"]):
            for device in devices:
                if "AP-" not in device.upper():
                    continue
                commands.append(
                    ControlCommand(
                        command_type="ap_reachability_check",
                        target=device,
                        command=f"ap_reachability_check --ap {device} --include-ping --include-snmp",
                        risk_level="normal",
                        requires_approval=False,
                        rationale="低风险只读动作：确认 AP 是否在线以及监控采集是否可达。",
                    )
                )
                commands.append(
                    ControlCommand(
                        command_type="poe_power_cycle",
                        target=device,
                        command=f"poe_power_cycle --ap {device} --dry-run",
                        risk_level="warning",
                        requires_approval=True,
                        rationale="中风险动作：PoE 断电重启会影响该 AP 下终端，需审批后执行。",
                    )
                )

        if "丢包" in text or "packet_loss" in text or "链路" in text:
            for device in devices:
                commands.append(
                    ControlCommand(
                        command_type="interface_error_audit",
                        target=device,
                        command=f"interface_error_audit --device {device} --window 30m",
                        risk_level="normal",
                        requires_approval=False,
                        rationale="低风险只读动作：检查接口错误包、丢包和链路抖动。",
                    )
                )

        if "拥塞" in text or "带宽" in text or "connections" in text:
            for device in devices:
                commands.append(
                    ControlCommand(
                        command_type="traffic_topn_audit",
                        target=device,
                        command=f"traffic_topn_audit --device {device} --window 15m --top 10",
                        risk_level="normal",
                        requires_approval=False,
                        rationale="低风险只读动作：确认热点业务或异常大流量终端。",
                    )
                )

        if diagnosis.risk_level == "critical" and any("SW-" in device.upper() for device in devices):
            for device in devices:
                if "SW-" not in device.upper():
                    continue
                commands.append(
                    ControlCommand(
                        command_type="prepare_link_failover",
                        target=device,
                        command=f"prepare_link_failover --device {device} --dry-run",
                        risk_level="critical",
                        requires_approval=True,
                        rationale="高风险动作：链路切换必须经安全审查和人工审批，本阶段只生成 dry-run 命令。",
                    )
                )

        if not commands:
            commands.append(
                ControlCommand(
                    command_type="manual_review_ticket",
                    target=diagnosis.location or "unknown",
                    command=f"create_manual_review_ticket --event {diagnosis.event_id}",
                    risk_level="normal",
                    requires_approval=False,
                    rationale="证据不足时创建人工复核任务。",
                )
            )
        return commands

    @staticmethod
    def _target_devices(diagnosis: DiagnosisResult) -> list[str]:
        devices = [device for device in diagnosis.suspect_devices if device]
        topology_devices = diagnosis.evidence.get("topology", {}).get("devices", [])
        if not devices and isinstance(topology_devices, list):
            for item in topology_devices:
                if isinstance(item, dict):
                    name = item.get("device_id") or item.get("name")
                    if name:
                        devices.append(str(name))
        if not devices:
            for cause in diagnosis.possible_causes:
                for token in cause.replace("，", " ").replace("。", " ").split():
                    normalized = token.strip(":：,，")
                    if normalized.upper().startswith(("AP-", "SW-")):
                        devices.append(normalized.upper())
        text_sources = [
            diagnosis.summary,
            diagnosis.final_reasoning,
            diagnosis.issue_desc,
            *diagnosis.possible_causes,
            *diagnosis.recommendations,
        ]
        for text in text_sources:
            if not text:
                continue
            for match in re.findall(r"\b(?:AP|SW)-[A-Za-z0-9-]+\b", text, flags=re.IGNORECASE):
                devices.append(match.upper())
        return list(dict.fromkeys(devices))
