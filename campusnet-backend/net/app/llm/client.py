"""vLLM OpenAI 兼容客户端封装。"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI

from app.config import settings


_DISABLE_THINKING_EXTRA_BODY = {"enable_thinking": False}


def _build_sync_http_client() -> httpx.Client:
    """创建同步 HTTP 客户端。

    默认关闭 `trust_env`，避免系统错误代理（如 127.0.0.1:9）导致模型连接失败。
    """

    return httpx.Client(
        timeout=settings.request_timeout,
        trust_env=not settings.disable_env_proxy,
    )


def _build_async_http_client() -> httpx.AsyncClient:
    """创建异步 HTTP 客户端。"""

    return httpx.AsyncClient(
        timeout=settings.request_timeout,
        trust_env=not settings.disable_env_proxy,
    )


def build_fast_llm() -> ChatOpenAI:
    """创建用于意图识别与 FAQ 的快速模型客户端。

    Returns:
        ChatOpenAI: 指向本地 vLLM API 的轻量模型实例。
    """

    fast_llm = ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=0.0,
        timeout=settings.request_timeout,
        max_retries=1,
        http_client=_build_sync_http_client(),
        http_async_client=_build_async_http_client(),
        extra_body=_DISABLE_THINKING_EXTRA_BODY,
    )
    return fast_llm


def build_deep_llm() -> ChatOpenAI:
    """创建用于复杂故障推理的深度模型客户端。

    Returns:
        ChatOpenAI: 指向本地 vLLM API 的深度模型实例。
    """

    reasoning_llm = ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=0.6,
        timeout=settings.request_timeout,
        max_retries=1,
        http_client=_build_sync_http_client(),
        http_async_client=_build_async_http_client(),
        extra_body=_DISABLE_THINKING_EXTRA_BODY,
    )
    return reasoning_llm
