"""DiagnosisAgent 自主诊断图（动态 MCP 工具版）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.nodes import DiagnosisFunctionNodes
from app.agent.state import AgentState
from app.agent.tools import build_hybrid_mcp_tools
from app.llm.client import build_deep_llm
from app.mcp.client import get_standard_mcp_manager

logger = logging.getLogger(__name__)


async def build_diagnosis_graph() -> Any:
    """构建 DiagnosisAgent 图：`call_model <-> tool_node`。"""

    manager = get_standard_mcp_manager()
    tools = await build_hybrid_mcp_tools(manager=manager)
    llm_plain = build_deep_llm()
    max_tool_turns = 30

    if tools:
        logger.info("Binding %d remote MCP tools to LLM.", len(tools))
        llm_with_tools = llm_plain.bind_tools(tools)
        tool_node: ToolNode | None = ToolNode(tools)
    else:
        logger.warning("No MCP tools discovered. Diagnosis graph will run LLM-only.")
        llm_with_tools = llm_plain
        tool_node = None

    nodes = DiagnosisFunctionNodes(
        llm_with_tools=llm_with_tools,
        tool_node=tool_node,
        llm_plain=llm_plain,
    )

    def _tool_call_signature(msg: AIMessage) -> str:
        return json.dumps(msg.tool_calls, ensure_ascii=False, sort_keys=True)

    def route_after_model(state: AgentState) -> str:
        last_msg = state["messages"][-1]
        if tool_node is not None and isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            ai_with_tools = [
                msg
                for msg in state["messages"]
                if isinstance(msg, AIMessage) and msg.tool_calls
            ]
            if len(ai_with_tools) >= max_tool_turns:
                logger.warning(
                    "Tool-call turns reached limit (%d), routing to force_finalize.",
                    max_tool_turns,
                )
                return "force_finalize"

            if len(ai_with_tools) >= 2:
                if _tool_call_signature(ai_with_tools[-1]) == _tool_call_signature(ai_with_tools[-2]):
                    logger.warning(
                        "Detected repeated identical tool_calls, routing to force_finalize."
                    )
                    return "force_finalize"

            return "tool_node"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("call_model", nodes.call_model)
    workflow.add_node("tool_node", nodes.run_tools)
    workflow.add_node("force_finalize", nodes.force_finalize)

    workflow.add_edge(START, "call_model")
    workflow.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "tool_node": "tool_node",
            "force_finalize": "force_finalize",
            END: END,
        },
    )
    workflow.add_edge("tool_node", "call_model")
    workflow.add_edge("force_finalize", END)

    return workflow.compile()
