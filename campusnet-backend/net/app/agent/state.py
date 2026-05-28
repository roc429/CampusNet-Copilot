"""DiagnosisAgent 内部 LangGraph 状态定义。"""

from __future__ import annotations

from typing import Annotated, TypedDict

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
