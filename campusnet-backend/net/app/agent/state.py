"""DiagnosisAgent 内部 LangGraph 状态定义。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """DiagnosisAgent 微观状态机数据结构。

    Attributes:
        messages: 对话历史与工具消息,LangGraph 通过 add_messages 自动聚合。
        event_id: 异常事件 ID。
        location: 故障地点。
        issue_desc: 故障描述。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    event_id: str
    location: str
    issue_desc: str


class OpsWorkflowState(TypedDict, total=False):
    """DiagnosisAgent 宏观运维闭环状态机数据结构。

    该状态图负责编排诊断后的闭环流程：是否需要修复、生成计划、
    安全审查、审批等待、控制命令 dry-run、验证和最终报告生成。
    """

    diagnosis_result: Any
    requires_remediation: bool
    remediation_plan: Any
    remediation_closure: Any
    approval_rejected: bool
    execution_results: list[dict[str, Any]]
    verification: dict[str, Any]
    error: str
