"""Rule-based router for foreground chat traffic."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.service import LLMService


@dataclass(slots=True)
class ChatRouteResult:
    intent: str
    event_type: str | None = None
    confidence: float = 0.0
    location_hint: str | None = None
    device_id: str | None = None
    metric: str | None = None
    symptom: str | None = None
    reason: str = ""


class ChatRouter:
    """Classify chat questions into direct answer, RAG, or diagnosis routes."""

    simple_chat_keywords = ["你好", "你是谁", "你能做什么", "帮助", "怎么用"]
    knowledge_keywords = [
        "怎么处理",
        "常见原因",
        "如何判断",
        "配置方法",
        "操作步骤",
        "认证失败怎么办",
    ]
    campus_knowledge_keywords = [
        "校园网",
        "认证",
        "宿舍区",
        "图书馆",
        "教学楼",
        "AP负载",
        "AP 负载",
        "无线覆盖",
        "Portal",
        "运维",
    ]
    direct_answer_keywords = ["什么是", "解释一下", "介绍一下", "原理", "区别"]
    status_keywords = ["现在", "当前", "哪里网不好", "网络怎么样", "卡不卡", "状态怎么样", "丢包严重吗"]
    forecast_keywords = ["明天", "后天", "今晚", "未来", "预测", "预计", "会不会", "怎么样"]
    fault_keywords = ["很卡", "断网", "掉线", "网页打不开", "连不上", "延迟很高", "丢包", "不能访问"]
    diagnosis_keywords = ["帮我分析", "为什么", "是不是", "可能原因", "根因", "排查", "诊断"]
    location_keywords = ["图书馆三楼", "图书馆", "宿舍区", "宿舍", "教学楼三楼", "教学楼"]
    metric_keywords = ["丢包", "延迟", "带宽", "负载", "连接数", "CPU", "出口链路"]
    allowed_intents = {
        "direct_answer",
        "simple_chat",
        "system_help",
        "knowledge_qa",
        "user_network_status_query",
        "user_fault_report",
        "user_diagnosis_request",
        "unclear",
    }

    def __init__(self, llm_service: "LLMService | None" = None, use_llm: bool = True) -> None:
        self.llm_service = llm_service
        self.use_llm = use_llm
        self.logger = logging.getLogger(self.__class__.__name__)

    async def classify(self, question: str) -> ChatRouteResult:
        if self.use_llm:
            try:
                route = await self._classify_with_llm(question)
                if route.confidence >= 0.55 and route.intent != "unclear":
                    return route
                self.logger.info(
                    "LLM chat route confidence too low, falling back to rules. intent=%s confidence=%.2f",
                    route.intent,
                    route.confidence,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("LLM chat route failed, falling back to rules: %s", exc)
        return self._classify_by_rules(question)

    async def _classify_with_llm(self, question: str) -> ChatRouteResult:
        service = self._ensure_llm_service()
        raw = await service.classify_chat_route(question)
        if not isinstance(raw, dict):
            raise ValueError(f"LLM route result is not a JSON object: {raw!r}")
        route = self._route_from_payload(raw)
        if route.intent == "system_help":
            route.intent = "direct_answer"
        return route

    def _ensure_llm_service(self) -> "LLMService":
        if self.llm_service is None:
            from app.llm.service import LLMService

            self.llm_service = LLMService()
        return self.llm_service

    def _route_from_payload(self, payload: dict[str, Any]) -> ChatRouteResult:
        intent = str(payload.get("intent") or "unclear").strip()
        if intent not in self.allowed_intents:
            intent = "unclear"
        event_type = payload.get("event_type")
        event_type = str(event_type).strip() if event_type not in (None, "", "null") else None
        if intent in {"user_network_status_query", "user_fault_report", "user_diagnosis_request"}:
            event_type = event_type or intent
        else:
            event_type = None
        confidence = self._coerce_confidence(payload.get("confidence"))
        return ChatRouteResult(
            intent=intent,
            event_type=event_type,
            confidence=confidence,
            location_hint=self._nullable_str(payload.get("location_hint")),
            device_id=self._nullable_str(payload.get("device_id")),
            metric=self._nullable_str(payload.get("metric")),
            symptom=self._nullable_str(payload.get("symptom")),
            reason=self._nullable_str(payload.get("reason")) or "轻量模型分类",
        )

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _nullable_str(value: Any) -> str | None:
        if value in (None, "", "null"):
            return None
        return str(value).strip() or None

    def _classify_by_rules(self, question: str) -> ChatRouteResult:
        text = question.strip()
        if not text:
            return ChatRouteResult(intent="unclear", reason="空问题")

        location_hint = self._first_match(text, self.location_keywords)
        metric = self._first_match(text, self.metric_keywords)
        device_id = self._extract_device_id(text)
        symptom = self._extract_symptom(text)

        if self._contains(text, self.simple_chat_keywords):
            return ChatRouteResult(
                intent="direct_answer",
                confidence=0.92,
                reason="用户询问系统能力或普通问候",
            )

        has_fault = self._contains(text, self.fault_keywords)
        has_diagnosis = self._contains(text, self.diagnosis_keywords)
        has_status = self._contains(text, self.status_keywords) or device_id is not None
        has_forecast = self._contains(text, self.forecast_keywords)

        if has_forecast and (location_hint or "网络" in text or "WiFi" in text or device_id):
            return ChatRouteResult(
                intent="user_diagnosis_request",
                event_type="user_diagnosis_request",
                confidence=0.88,
                location_hint=location_hint,
                device_id=device_id,
                metric=metric,
                symptom=symptom,
                reason="用户询问未来网络状态，需要 Prometheus 历史指标与 TimesFM 预测",
            )

        has_explicit_hypothesis = any(keyword in text for keyword in ["是不是", "为什么", "根因", "排查", "诊断", "出口链路"])
        if has_diagnosis and has_explicit_hypothesis and (location_hint or metric or has_fault or "网络" in text or "WiFi" in text):
            return ChatRouteResult(
                intent="user_diagnosis_request",
                event_type="user_diagnosis_request",
                confidence=0.86,
                location_hint=location_hint,
                device_id=device_id,
                metric=metric,
                symptom=symptom,
                reason="用户要求深度网络诊断",
            )

        if has_fault:
            return ChatRouteResult(
                intent="user_fault_report",
                event_type="user_fault_report",
                confidence=0.84,
                location_hint=location_hint,
                device_id=device_id,
                metric=metric,
                symptom=symptom,
                reason="用户主动报障",
            )

        if has_status:
            return ChatRouteResult(
                intent="user_network_status_query",
                event_type="user_network_status_query",
                confidence=0.82,
                location_hint=location_hint,
                device_id=device_id,
                metric=metric,
                symptom=symptom,
                reason="用户查询当前网络状态",
            )

        if self._contains(text, self.knowledge_keywords) and self._contains(text, self.campus_knowledge_keywords):
            return ChatRouteResult(
                intent="knowledge_qa",
                confidence=0.85,
                reason="用户询问校园知识库或校园网运维经验",
            )

        if self._contains(text, self.direct_answer_keywords):
            return ChatRouteResult(
                intent="direct_answer",
                confidence=0.82,
                reason="用户询问通用概念，直接由模型回答",
            )

        return ChatRouteResult(
            intent="unclear",
            confidence=0.35,
            location_hint=location_hint,
            device_id=device_id,
            metric=metric,
            symptom=symptom,
            reason="无法可靠判断用户意图",
        )

    @staticmethod
    def _contains(text: str, keywords: list[str]) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    @staticmethod
    def _first_match(text: str, keywords: list[str]) -> str | None:
        lowered = text.lower()
        for keyword in keywords:
            if keyword.lower() in lowered:
                return keyword
        return None

    @staticmethod
    def _extract_device_id(text: str) -> str | None:
        for token in text.replace("，", " ").replace("。", " ").split():
            normalized = token.strip("？?：:")
            if normalized.upper().startswith(("AP-", "SW-")):
                return normalized.upper()
        return None

    def _extract_symptom(self, text: str) -> str | None:
        matches = [keyword for keyword in self.fault_keywords if keyword in text]
        return "，".join(matches) if matches else None
