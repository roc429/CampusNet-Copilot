"""ChatAgent：前台客服问答智能体。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.agents.chat_router import ChatRouteResult, ChatRouter
from app.mcp_clients.rag_client import KnowledgeChunk, search_knowledge_base
from app.schemas import AnomalyEvent

if TYPE_CHECKING:
    from app.llm.service import LLMService
    from app.stores import OpsMemoryStore


class ChatAgent:
    """面向用户咨询的低延迟问答组件。"""

    def __init__(
        self,
        anomaly_queue: asyncio.Queue[AnomalyEvent] | None = None,
        llm_service: "LLMService | None" = None,
        router: ChatRouter | None = None,
        store: "OpsMemoryStore | None" = None,
    ) -> None:
        self.anomaly_queue = anomaly_queue
        self.llm_service = llm_service
        self.router = router or ChatRouter()
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)
        self.latest_diagnosis_event_id: str | None = None

    async def answer(self, user_id: str, question: str) -> str:
        """处理单轮问答。"""

        self.logger.info("Chat request received user_id=%s question=%s", user_id, question)
        try:
            route = await self.router.classify(question)
        except Exception:  # noqa: BLE001
            self.logger.exception("ChatRouter classify failed user_id=%s", user_id)
            return await self._answer_directly(question)

        self.logger.info(
            "Chat route user_id=%s intent=%s event_type=%s confidence=%.2f",
            user_id,
            route.intent,
            route.event_type,
            route.confidence,
        )

        if route.intent in {"direct_answer", "simple_chat", "system_help"}:
            return await self._answer_directly(question)
        if route.intent == "knowledge_qa":
            return await self._answer_with_rag(question)
        if route.intent in {
            "user_network_status_query",
            "user_fault_report",
            "user_diagnosis_request",
        }:
            return await self._enqueue_diagnosis_event(user_id, question, route)
        return await self._answer_directly(question)

    async def _answer_directly(self, question: str) -> str:
        service = self._ensure_llm_service()
        prompt = (
            "请直接回答用户问题。若是通用网络概念，请用简洁准确的方式解释；"
            "若用户询问本系统能力，可说明你能回答通用网络问题、检索校园知识库、并为实时故障创建后台诊断任务。\n"
            f"用户问题：{question}"
        )
        return await service.quick_reply(prompt)

    def _ensure_llm_service(self) -> "LLMService":
        if self.llm_service is None:
            from app.llm.service import LLMService

            self.llm_service = LLMService()
        return self.llm_service

    async def _answer_with_rag(self, question: str) -> str:
        try:
            chunks = await search_knowledge_base(question, top_k=3)
        except Exception:  # noqa: BLE001
            self.logger.exception("RAG search failed question=%s", question)
            return "知识库暂时不可用。通用建议：请先明确故障位置、影响范围、发生时间，并结合丢包、延迟、AP 负载和链路利用率判断。"

        if not chunks:
            return (
                "知识库中没有找到充分依据。"
                "当前尚未接入或创建可用于回答该问题的校园知识库，因此我不能把通用经验当作校内知识库结论。"
            )

        answer = self._build_knowledge_answer(chunks)
        evidence = "\n".join(
            f"{index}. {chunk.title}（{chunk.source}，score={chunk.score:.2f}）：{chunk.content}"
            for index, chunk in enumerate(chunks, start=1)
        )
        return f"{answer}\n\n知识库依据：\n{evidence}"

    @staticmethod
    def _build_knowledge_answer(chunks: list[KnowledgeChunk]) -> str:
        first = chunks[0]
        return f"直接答案：{first.content}"

    async def _enqueue_diagnosis_event(
        self,
        user_id: str,
        question: str,
        route: ChatRouteResult,
    ) -> str:
        if self.anomaly_queue is None:
            self.logger.error("Failed to enqueue diagnosis event: anomaly_queue is None")
            return "诊断任务创建失败：队列未初始化"

        event = AnomalyEvent(
            event_type=route.event_type or route.intent,
            source="chat",
            user_id=user_id,
            question=question,
            location_hint=route.location_hint,
            device_id=route.device_id,
            metric=route.metric,
            symptom=route.symptom,
            severity="info",
            location=route.location_hint or "",
            issue_desc=question,
            device_hint=route.device_id or "",
            metadata={
                "intent": route.intent,
                "route_reason": route.reason,
                "requires_forecast": any(word in question for word in ["明天", "后天", "今晚", "未来", "预测", "预计"]),
            },
        )
        try:
            await self.anomaly_queue.put(event)
            if self.store is not None:
                self.store.save_event(event)
        except Exception:  # noqa: BLE001
            self.logger.exception("Failed to enqueue diagnosis event user_id=%s", user_id)
            return "诊断任务创建失败，请稍后重试"

        self.logger.info(
            "Diagnosis event enqueued user_id=%s intent=%s event_type=%s event_id=%s",
            user_id,
            route.intent,
            event.event_type,
            event.event_id,
        )
        self.latest_diagnosis_event_id = event.event_id
        return (
            "我已将你的问题转为网络诊断任务，正在查询相关拓扑和实时指标。"
            f"任务 ID：{event.event_id}。你可以稍后通过 /reports/{event.event_id} 查看诊断结果。"
        )
