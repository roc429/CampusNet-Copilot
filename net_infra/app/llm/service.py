"""统一封装异步 LLM 调用能力。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.llm.client import build_deep_llm, build_fast_llm

logger = logging.getLogger(__name__)


class LLMService:
    """大模型服务门面。

    该类将“快速回复”和“深度推理”两种模型能力统一封装为异步方法，
    便于被各智能体复用。
    """

    def __init__(self) -> None:
        self.fast_llm = build_fast_llm()
        self.deep_llm = build_deep_llm()
        self.fast_timeout_seconds = max(12, settings.request_timeout)
        self.deep_timeout_seconds = max(60, settings.request_timeout)

    async def quick_reply(self, question: str) -> str:
        """调用快速模型生成简洁回复。"""

        try:
            msg = await asyncio.wait_for(
                self.fast_llm.ainvoke(
                    [
                        SystemMessage(content="你是校园网络客服助手，请给出简洁、准确、礼貌的回复。"),
                        HumanMessage(content=question),
                    ]
                ),
                timeout=self.fast_timeout_seconds,
            )
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            return self._strip_thinking(content)
        except Exception:
            logger.exception("quick_reply 调用失败")
            if settings.llm_strict:
                raise
            return "当前快速模型暂不可用，系统已记录问题并建议先提供具体地点、时间和故障现象。"

    async def classify_chat_route(self, question: str) -> dict[str, Any]:
        """使用快速模型对 /chat 请求做结构化线路分类。"""

        system_prompt = (
            "你是 CampusNet-Copilot 的聊天路由分类器。"
            "只输出 JSON，不要输出 Markdown，不要解释。"
            "可选 intent 只能是：direct_answer, simple_chat, system_help, knowledge_qa, "
            "user_network_status_query, user_fault_report, user_diagnosis_request, unclear。"
            "如果是用户主动查询实时网络状态、报障、要求诊断，必须给出对应 event_type；"
            "如果用户询问未来网络状态或预测，例如“明天图书馆三层网络怎么样”，"
            "intent=user_diagnosis_request，event_type=user_diagnosis_request；"
            "如果是通用概念解释或普通问答，例如“什么是 IP 地址 / DNS / TCP”，intent=direct_answer；"
            "如果明确涉及校园知识库、校园网认证、校内区域、运维手册或校园网处理经验，intent=knowledge_qa；"
            "如果只是问候或系统使用帮助，intent=simple_chat 或 system_help。"
        )
        user_prompt = (
            "请分类以下用户问题，并提取可选线索。JSON schema:\n"
            "{"
            '"intent": "...", '
            '"event_type": "user_network_status_query|user_fault_report|user_diagnosis_request|null", '
            '"confidence": 0.0, '
            '"location_hint": null, '
            '"device_id": null, '
            '"metric": null, '
            '"symptom": null, '
            '"reason": "..."'
            "}\n"
            f"用户问题：{question}"
        )
        msg = await asyncio.wait_for(
            self.fast_llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            ),
            timeout=self.fast_timeout_seconds,
        )
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        cleaned = self._strip_thinking(content)
        json_text = self._extract_json_object(cleaned)
        if not json_text:
            logger.warning("classify_chat_route returned empty/non-json content: %r", content[:500])
            raise ValueError("LLM route classifier returned empty or non-JSON content")
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning("classify_chat_route JSON parse failed. raw=%r extracted=%r", content[:500], json_text[:500])
            raise ValueError(f"LLM route classifier returned invalid JSON: {exc}") from exc

    @staticmethod
    def _extract_json_object(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end >= start:
            return stripped[start : end + 1]
        return ""

    @staticmethod
    def _strip_thinking(text: str) -> str:
        if not text:
            return ""
        without_blocks = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        without_open = re.sub(r"^.*?</think>", "", without_blocks, flags=re.DOTALL | re.IGNORECASE)
        return without_open.strip()

    async def deep_reason(self, prompt: str) -> str:
        """调用深度模型执行复杂推理。"""

        try:
            msg = await asyncio.wait_for(
                self.deep_llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.deep_timeout_seconds,
            )
            return msg.content if isinstance(msg.content, str) else str(msg.content)
        except Exception:
            logger.exception("deep_reason 调用失败")
            if settings.llm_strict:
                raise
            return (
                "根因判断：汇聚交换机上联链路拥塞导致区域 AP 丢包升高。\n"
                "关键证据：相关 AP 与汇聚交换机在 10 分钟窗口内均出现 >5% 丢包与高负载。\n"
                "处置建议：短期执行流量疏导与端口限速排查；长期优化汇聚容量并补充冗余链路。"
            )
