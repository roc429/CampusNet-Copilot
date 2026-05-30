"""DiagnosisAgent 节点实现（Function Calling 版）。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


class DiagnosisFunctionNodes:
    """封装 `call_model` 与 `tool_node` 的执行节点。"""

    def __init__(
        self,
        llm_with_tools: Any,
        tool_node: ToolNode | None,
        llm_plain: Any,
        progress_callback: Callable[[str, str, str, str], None] | None = None,
    ) -> None:
        self.llm_with_tools = llm_with_tools
        self.tool_node = tool_node
        self.llm_plain = llm_plain
        self.progress_callback = progress_callback

    async def call_model(self, state: AgentState) -> dict[str, Any]:
        """调用绑定工具后的 LLM。"""

        event_id = state.get("event_id", "unknown")
        self._emit_progress(
            event_id=event_id,
            stage="llm_reasoning",
            message="DiagnosisAgent 正在进行模型推理，判断是否需要调用 NetBox、Prometheus、TimesFM 等工具。",
        )
        response = await self.llm_with_tools.ainvoke(state["messages"])
        if isinstance(response, AIMessage) and response.tool_calls:
            logger.info(
                "Model emitted tool_calls: %s",
                json.dumps(response.tool_calls, ensure_ascii=False),
            )
            for tool_call in response.tool_calls:
                tool_name = str(tool_call.get("name", "unknown_tool"))
                args = tool_call.get("args", {})
                component, stage = self._tool_component_and_stage(tool_name)
                self._emit_progress(
                    event_id=event_id,
                    stage=f"{stage}_requested",
                    message=f"模型已请求调用 {component}：{tool_name}，正在准备执行。参数：{self._compact_json(args)}",
                )
        else:
            logger.info("Model emitted final response without tool_calls.")
            self._emit_progress(
                event_id=event_id,
                stage="llm_finalizing",
                message="模型已完成工具证据分析，正在生成诊断结论。",
            )
        return {"messages": [response]}

    async def run_tools(self, state: AgentState) -> dict[str, Any]:
        """执行 ToolNode，并打印调用与返回日志。"""

        if self.tool_node is None:
            logger.info("ToolNode skipped because no tools are bound.")
            return {"messages": []}

        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        self._rewrite_prometheus_numeric_device_ids(state, tool_calls)
        event_id = state.get("event_id", "unknown")
        for tool_call in tool_calls:
            tool_name = str(tool_call.get("name", "unknown_tool"))
            args = tool_call.get("args", {})
            component, stage = self._tool_component_and_stage(tool_name)
            self._emit_progress(
                event_id=event_id,
                stage=f"{stage}_running",
                message=f"正在调用 {component}：{tool_name}。参数：{self._compact_json(args)}",
            )
        logger.info(
            "ToolNode executing calls: %s",
            json.dumps(tool_calls, ensure_ascii=False),
        )

        result = await self.tool_node.ainvoke(state)
        returned_messages = result.get("messages", [])
        rendered_contents = [getattr(msg, "content", "") for msg in returned_messages]
        logger.info(
            "ToolNode returned messages: %s",
            json.dumps(
                rendered_contents,
                ensure_ascii=False,
            ),
        )
        for tool_call in tool_calls:
            tool_name = str(tool_call.get("name", "unknown_tool"))
            component, stage = self._tool_component_and_stage(tool_name)
            self._emit_progress(
                event_id=event_id,
                stage=f"{stage}_completed",
                message=f"{component} 工具调用完成：{tool_name}，诊断图正在合并工具返回结果。",
            )

        # 熔断保护：一轮工具全部失败时，明确要求模型停止继续调用工具并直接给出可执行建议。
        if returned_messages:
            all_failed = True
            for content in rendered_contents:
                try:
                    parsed = json.loads(content) if isinstance(content, str) else {}
                except json.JSONDecodeError:
                    parsed = {}
                if not isinstance(parsed, dict) or parsed.get("ok") is not False:
                    all_failed = False
                    break
            if all_failed:
                returned_messages = list(returned_messages) + [
                    HumanMessage(
                        content=(
                            "本轮工具调用均失败，请不要继续调用任何工具。"
                            "请基于已有信息直接输出诊断结论、可能根因和人工排查步骤。"
                        )
                    )
                ]
                return {"messages": returned_messages}

        return result

    def _emit_progress(self, event_id: str, stage: str, message: str, status: str = "running") -> None:
        if self.progress_callback is None:
            return
        self.progress_callback(event_id, stage, message, status)

    @staticmethod
    def _tool_component_and_stage(tool_name: str) -> tuple[str, str]:
        lowered = tool_name.lower()
        if "netbox" in lowered:
            return "NetBox MCP 拓扑查询", "tool_netbox"
        if "prometheus" in lowered or "metric" in lowered or "query" in lowered or "promql" in lowered:
            return "Prometheus MCP 指标查询", "tool_prometheus"
        if "timesfm" in lowered or "forecast" in lowered or "anomaly" in lowered:
            return "TimesFM MCP 预测分析", "tool_timesfm"
        if "rag" in lowered or "knowledge" in lowered:
            return "RAG 知识库检索", "tool_rag"
        if "grafana" in lowered or "dashboard" in lowered:
            return "Grafana MCP 看板查询", "tool_grafana"
        return "MCP 工具", "tool_mcp"

    @staticmethod
    def _compact_json(payload: Any, limit: int = 240) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except TypeError:
            text = str(payload)
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    @staticmethod
    def _rewrite_prometheus_numeric_device_ids(state: AgentState, tool_calls: list[dict[str, Any]]) -> None:
        """Prometheus uses device name labels, not NetBox numeric primary keys."""

        id_to_name = DiagnosisFunctionNodes._extract_netbox_id_name_map(state)
        if not id_to_name:
            return
        for call in tool_calls:
            name = str(call.get("name", "")).lower()
            if "get_device_metrics" not in name:
                continue
            args = call.get("args")
            if not isinstance(args, dict):
                continue
            device_ids = args.get("device_ids")
            if not isinstance(device_ids, list):
                continue
            rewritten = [id_to_name.get(str(item), item) for item in device_ids]
            if rewritten != device_ids:
                logger.info(
                    "Rewriting Prometheus device_ids from NetBox numeric ids: %s -> %s",
                    device_ids,
                    rewritten,
                )
                args["device_ids"] = rewritten

    @staticmethod
    def _extract_netbox_id_name_map(state: AgentState) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for msg in state.get("messages", []):
            content = getattr(msg, "content", "")
            if not isinstance(content, str) or "netbox" not in content.lower():
                continue
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                continue
            DiagnosisFunctionNodes._collect_id_name_pairs(payload, mapping)
        return mapping

    @staticmethod
    def _collect_id_name_pairs(payload: Any, mapping: dict[str, str]) -> None:
        if isinstance(payload, dict):
            item_id = payload.get("id")
            item_name = payload.get("name")
            if isinstance(item_id, int | str) and isinstance(item_name, str) and item_name:
                mapping[str(item_id)] = item_name
            for value in payload.values():
                DiagnosisFunctionNodes._collect_id_name_pairs(value, mapping)
        elif isinstance(payload, list):
            for item in payload:
                DiagnosisFunctionNodes._collect_id_name_pairs(item, mapping)

    async def force_finalize(self, state: AgentState) -> dict[str, Any]:
        """当工具调用陷入循环时，强制模型停止调用工具并输出最终结论。"""

        logger.warning("Force finalization triggered to avoid tool-call recursion.")
        prompt = HumanMessage(
            content=(
                "请立即停止任何工具调用。"
                "基于当前已知上下文，直接输出最终诊断结论、证据不足说明与人工处置建议。"
            )
        )
        response = await self.llm_plain.ainvoke([*state["messages"], prompt])
        return {"messages": [response]}
