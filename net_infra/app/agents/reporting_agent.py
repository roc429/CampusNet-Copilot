"""ReportingAgent：生成运维简报并输出到报告队列。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from app.schemas import DiagnosisResult, OpsReport

if TYPE_CHECKING:
    from app.llm.service import LLMService
    from app.stores import OpsMemoryStore


class ReportingAgent:
    """消费诊断结果并生成人性化报告。"""

    def __init__(
        self,
        diagnosis_queue: asyncio.Queue[DiagnosisResult],
        report_queue: asyncio.Queue[OpsReport],
        llm_service: "LLMService | None" = None,
        store: "OpsMemoryStore | None" = None,
    ) -> None:
        self.diagnosis_queue = diagnosis_queue
        self.report_queue = report_queue
        self.llm_service = llm_service
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    async def run(self) -> None:
        """持续生成运维报告。"""

        while True:
            diagnosis = await self.diagnosis_queue.get()
            try:
                self.logger.info("Consumed DiagnosisResult event_id=%s", diagnosis.event_id)
                if self.store is not None:
                    self.store.save_diagnosis(diagnosis)
                report_text = await self._build_report(diagnosis)
                report = OpsReport(
                    event_id=diagnosis.event_id,
                    report_text=report_text,
                    event_type=diagnosis.event_type,
                    source=diagnosis.source,
                )
                if self.store is not None:
                    self.store.save_report(report)
                await self.report_queue.put(report)
                self.logger.info("OpsReport enqueued event_id=%s", diagnosis.event_id)
            finally:
                self.diagnosis_queue.task_done()

    async def _build_report(self, diagnosis: DiagnosisResult) -> str:
        base_report = self._build_template_report(diagnosis, llm_status="not_called")
        if self._diagnosis_used_langgraph_llm(diagnosis):
            return self._build_final_user_report(diagnosis)
        if diagnosis.source != "chat":
            return base_report
        try:
            llm = self._ensure_llm_service()
            prompt = self._build_llm_report_prompt(diagnosis)
            llm_report = await llm.quick_reply(prompt)
            if llm_report.strip():
                return self._with_llm_status(llm_report.strip(), diagnosis, llm_status="ok")
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("LLM report generation failed event_id=%s", diagnosis.event_id)
            return (
                self._build_template_report(diagnosis, llm_status=f"failed: {type(exc).__name__}")
                + "\n\n模型调用说明：\nLLM 报告生成失败，已回退到规则模板报告。"
            )
        return base_report

    def _build_final_user_report(self, diagnosis: DiagnosisResult) -> str:
        question = diagnosis.question or diagnosis.issue_desc or "未提供"
        body = self._strip_process_sections(diagnosis.summary or diagnosis.final_reasoning)
        risk_level = self._extract_or_default_risk(body, diagnosis.risk_level)
        if not body:
            body = diagnosis.summary or diagnosis.final_reasoning or "暂无诊断结论。"
        if diagnosis.evidence.get("remediation_closure") and body.startswith("任务 ID："):
            return body.strip()
        return (
            f"任务 ID：{diagnosis.event_id}\n\n"
            f"用户问题：\n{question}\n\n"
            f"风险等级：\n{risk_level}\n\n"
            f"{body.strip()}"
        )

    def _build_template_report(self, diagnosis: DiagnosisResult, llm_status: str) -> str:
        tool_trace_text = self._format_tool_trace(
            diagnosis.evidence.get("tool_calls", []),
            llm_status=llm_status,
        )
        topology_text = self._format_topology(diagnosis.evidence.get("topology", {}))
        metrics_text = self._format_metrics(diagnosis.evidence.get("metrics", {}))
        knowledge_text = self._format_knowledge(diagnosis.evidence.get("knowledge", []))
        missing_text = self._format_missing(diagnosis.missing_evidence)
        causes = self._numbered(diagnosis.possible_causes) or "暂无明确可能原因。"
        recommendations = self._numbered(diagnosis.recommendations) or "暂无建议操作。"
        question = diagnosis.question or diagnosis.issue_desc or "未提供"

        return (
            f"任务 ID：{diagnosis.event_id}\n\n"
            f"用户问题：\n{question}\n\n"
            f"诊断摘要：\n{diagnosis.summary or diagnosis.final_reasoning}\n\n"
            f"风险等级：\n{diagnosis.risk_level}\n\n"
            f"调用链路：\n{tool_trace_text}\n\n"
            f"拓扑证据：\n{topology_text}\n\n"
            f"指标证据：\n{metrics_text}\n\n"
            f"知识库证据：\n{knowledge_text}\n\n"
            f"可能原因：\n{causes}\n\n"
            f"建议操作：\n{recommendations}\n\n"
            f"缺失证据说明：\n{missing_text}"
        )

    def _ensure_llm_service(self) -> "LLMService":
        if self.llm_service is None:
            from app.llm.service import LLMService

            self.llm_service = LLMService()
        return self.llm_service

    def _build_llm_report_prompt(self, diagnosis: DiagnosisResult) -> str:
        payload = {
            "event_id": diagnosis.event_id,
            "event_type": diagnosis.event_type,
            "source": diagnosis.source,
            "question": diagnosis.question or diagnosis.issue_desc,
            "summary": diagnosis.summary,
            "risk_level": diagnosis.risk_level,
            "evidence": self._evidence_without_tool_calls(diagnosis.evidence),
            "possible_causes": diagnosis.possible_causes,
            "recommendations": diagnosis.recommendations,
            "missing_evidence": diagnosis.missing_evidence,
        }
        return (
            "你是校园网运维报告生成助手。请只基于下面 JSON 中的证据生成中文运维报告，"
            "禁止新增 JSON 中没有的设备、指标、数值、原因或结论。"
            "如果证据缺失，必须明确写“暂时不可用”。"
            "请不要生成“调用链路”段，调用链路将由系统追加。"
            "报告必须包含：任务 ID、用户问题、诊断摘要、风险等级、拓扑证据、"
            "指标证据、知识库证据、可能原因、建议操作、缺失证据说明。\n\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    def _with_llm_status(self, llm_report: str, diagnosis: DiagnosisResult, llm_status: str) -> str:
        tool_trace_text = self._format_tool_trace(
            diagnosis.evidence.get("tool_calls", []),
            llm_status=llm_status,
        )
        return f"{llm_report}\n\n调用链路：\n{tool_trace_text}"

    @staticmethod
    def _evidence_without_tool_calls(evidence: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in evidence.items() if key != "tool_calls"}

    @staticmethod
    def _strip_process_sections(text: str) -> str:
        if not text:
            return ""
        blocked_keywords = [
            "已调用工具",
            "调用工具",
            "调用链路",
            "工具 |",
            "工具|",
            "| 工具",
            "Tool",
        ]
        resume_keywords = [
            "关键证据",
            "可能原因",
            "建议操作",
            "缺失证据",
            "诊断摘要",
            "风险等级",
            "结论",
        ]
        kept: list[str] = []
        skipping = False
        for line in text.splitlines():
            stripped = line.strip()
            is_heading = stripped.startswith("#")
            if any(keyword in stripped for keyword in blocked_keywords):
                skipping = True
                continue
            if skipping and is_heading and any(keyword in stripped for keyword in resume_keywords):
                skipping = False
            if skipping:
                continue
            kept.append(line)
        cleaned = "\n".join(kept)
        return cleaned.replace("🛠️", "").replace("🔧", "").strip()

    @staticmethod
    def _extract_or_default_risk(text: str, fallback: str) -> str:
        if "高" in text or fallback == "critical":
            return "critical"
        if "中" in text or fallback == "warning":
            return "warning"
        if "低" in text or fallback == "normal":
            return "normal"
        return fallback

    @staticmethod
    def _format_topology(topology: dict[str, Any]) -> str:
        if not topology:
            return "拓扑证据暂时不可用。"
        devices = topology.get("devices", [])
        if not devices or any(device.get("source") == "mock_fallback" for device in devices):
            return "拓扑证据暂时不可用。"
        lines = [
            f"{index}. {device.get('device_id')}（{device.get('role', 'unknown')}，{device.get('location', 'unknown')}）"
            for index, device in enumerate(devices, start=1)
        ]
        return "\n".join(lines) if lines else "拓扑证据暂时不可用。"

    @staticmethod
    def _format_metrics(metrics: dict[str, Any]) -> str:
        if not metrics:
            return "实时指标暂时不可用。"
        lines: list[str] = []
        for device_id, values in metrics.items():
            packet_loss = ReportingAgent._metric_value(values, "packet_loss")
            ap_load = ReportingAgent._metric_value(values, "ap_load")
            bandwidth_out = ReportingAgent._metric_value(values, "bandwidth_out")
            latency = ReportingAgent._metric_value(values, "latency")
            lines.append(
                f"- {device_id}: packet_loss={packet_loss}, ap_load={ap_load}, "
                f"bandwidth_out={bandwidth_out}, latency={latency}"
            )
        return "\n".join(lines) if lines else "实时指标暂时不可用。"

    @staticmethod
    def _metric_value(values: dict[str, Any], metric: str) -> str:
        payload = values.get(metric, {})
        if not isinstance(payload, dict):
            return "N/A"
        source = payload.get("source", "unknown")
        value = payload.get("value")
        if source == "mock_fallback":
            return "N/A(mock_fallback ignored)"
        if value is None:
            return f"N/A({source})"
        return f"{value}({source})"

    @staticmethod
    def _format_knowledge(knowledge: list[Any]) -> str:
        if not knowledge:
            return "知识库证据暂时不可用或本次未调用。"
        return "\n".join(
            f"{index}. {item.get('title')}（{item.get('source')}，score={item.get('score')}）：{item.get('content')}"
            for index, item in enumerate(knowledge, start=1)
            if isinstance(item, dict)
        )

    @staticmethod
    def _format_missing(missing: list[str]) -> str:
        if not missing:
            return "无。"
        mapping = {
            "topology": "拓扑证据暂时不可用",
            "metrics": "实时指标暂时不可用",
            "knowledge": "知识库证据暂时不可用",
        }
        return "\n".join(f"- {mapping.get(item, item)}" for item in missing)

    @staticmethod
    def _format_tool_trace(tool_calls: list[Any], llm_status: str = "not_called") -> str:
        if not tool_calls:
            return "暂无调用链路记录。"
        lines: list[str] = []
        for index, item in enumerate(tool_calls, start=1):
            if not isinstance(item, dict):
                continue
            status = item.get("status", "unknown")
            detail = item.get("detail", "")
            if item.get("component") == "LLM":
                status = llm_status
                if llm_status == "ok":
                    detail = "模型已基于 DiagnosisResult 生成报告，要求不得新增工具证据。"
                elif llm_status == "ok_diagnosis_agent":
                    status = "ok"
                    detail = "DiagnosisAgent LangGraph 已调用模型进行工具诊断；ReportingAgent 未二次调用模型。"
                elif llm_status == "not_called":
                    detail = "非 chat 来源或模型未启用时不调用。"
            lines.append(
                f"{index}. {item.get('component', 'unknown')} -> {item.get('tool', 'unknown')}："
                f"{status}；{detail}"
            )
        return "\n".join(lines) if lines else "暂无调用链路记录。"

    @staticmethod
    def _numbered(items: list[str]) -> str:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))

    @staticmethod
    def _diagnosis_used_langgraph_llm(diagnosis: DiagnosisResult) -> bool:
        tool_calls = diagnosis.evidence.get("tool_calls", [])
        return any(
            isinstance(item, dict)
            and item.get("component") == "LLM"
            and item.get("tool") == "LangGraph.call_model"
            for item in tool_calls
        )
