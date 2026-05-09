"""调用阿里云百炼 DashScope OpenAI 兼容接口。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
from fastapi import HTTPException, status

SYSTEM_PROMPT = (
    "你是「小智士」校园网络运维助手，语气专业、简洁、友善。"
    "协助用户进行校园网络相关问答、使用指引与知识说明；不确定时请说明并建议联系现场运维。"
)


def _resolve_model(requested: str, deep_think: bool) -> str:
    """深度思考时避免使用可能不兼容思考参数的轻量模型。"""
    if deep_think and requested == "qwen-flash":
        return "qwen-plus"
    return requested


def _dashscope_error_message(data: dict[str, Any]) -> str:
    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return "DashScope 接口返回错误"


def _accumulate_chunk(obj: dict[str, Any]) -> tuple[str, str]:
    """从流式或单次 chunk 中提取 reasoning_content 与 content 增量。"""
    r_add, c_add = "", ""
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return r_add, c_add
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        return r_add, c_add

    delta = ch0.get("delta")
    if isinstance(delta, dict):
        rc = delta.get("reasoning_content")
        if isinstance(rc, str):
            r_add += rc
        co = delta.get("content")
        if isinstance(co, str):
            c_add += co

    msg = ch0.get("message")
    if isinstance(msg, dict):
        rc = msg.get("reasoning_content")
        if isinstance(rc, str):
            r_add += rc
        co = msg.get("content")
        if isinstance(co, str):
            c_add += co

    return r_add, c_add


def _parse_sse_data_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        out = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def _complete_chat_non_stream(
    *,
    url: str,
    api_key: str,
    messages: list[dict[str, str]],
    used_model: str,
    deep_think: bool,
) -> tuple[str, str, None]:
    body: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "enable_thinking": deep_think,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"无法连接模型服务：{exc}",
        ) from exc

    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="模型服务返回非 JSON 响应",
        )

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_dashscope_error_message(data if isinstance(data, dict) else {}),
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="模型响应格式异常",
        )

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_dashscope_error_message(data),
        )

    first = choices[0]
    if not isinstance(first, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="模型响应格式异常",
        )

    msg = first.get("message")
    if not isinstance(msg, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="模型响应格式异常",
        )

    content = msg.get("content")
    if not isinstance(content, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="模型未返回文本内容",
        )

    return content.strip() or "（模型返回为空）", used_model, None


def _complete_chat_stream_aggregate(
    *,
    url: str,
    api_key: str,
    messages: list[dict[str, str]],
    used_model: str,
) -> tuple[str, str, str | None]:
    """深度思考：流式聚合 reasoning_content 与正文（百炼推荐方式）。"""
    body: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "enable_thinking": True,
        "stream": True,
    }
    reasoning_parts: list[str] = []
    content_parts: list[str] = []

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/event-stream",
                },
                json=body,
            ) as resp:
                if resp.status_code >= 400:
                    raw = resp.read().decode("utf-8", errors="replace")
                    try:
                        err_obj = json.loads(raw)
                        detail = (
                            _dashscope_error_message(err_obj)
                            if isinstance(err_obj, dict)
                            else raw[:800]
                        )
                    except json.JSONDecodeError:
                        detail = raw[:800] if raw.strip() else f"HTTP {resp.status_code}"
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=detail,
                    )

                for line in resp.iter_lines():
                    if not line:
                        continue
                    obj = _parse_sse_data_line(line)
                    if obj is None:
                        continue
                    if obj.get("error"):
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=_dashscope_error_message(obj),
                        )
                    r_add, c_add = _accumulate_chunk(obj)
                    if r_add:
                        reasoning_parts.append(r_add)
                    if c_add:
                        content_parts.append(c_add)
    except HTTPException:
        raise
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"无法连接模型服务：{exc}",
        ) from exc

    reasoning = "".join(reasoning_parts).strip() or None
    content = "".join(content_parts).strip() or "（模型返回为空）"
    return content, used_model, reasoning


def forward_dashscope_sse(
    *,
    url: str,
    api_key: str,
    messages: list[dict[str, str]],
    model: str,
    deep_think: bool,
) -> Iterator[str]:
    """将百炼 SSE 原样以小块转发给前端（每行后补 \\n\\n 便于解析）。"""
    used_model = _resolve_model(model, deep_think)
    body: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "enable_thinking": deep_think,
        "stream": True,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/event-stream",
                },
                json=body,
            ) as resp:
                if resp.status_code >= 400:
                    raw = resp.read().decode("utf-8", errors="replace")
                    try:
                        err_obj = json.loads(raw)
                        detail = (
                            _dashscope_error_message(err_obj)
                            if isinstance(err_obj, dict)
                            else raw[:800]
                        )
                    except json.JSONDecodeError:
                        detail = raw[:800] if raw.strip() else f"HTTP {resp.status_code}"
                    err_line = json.dumps(
                        {"error": {"message": detail}},
                        ensure_ascii=False,
                    )
                    yield f"data: {err_line}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                for line in resp.iter_lines():
                    if line:
                        yield f"{line}\n\n"
    except httpx.RequestError as exc:
        err_line = json.dumps(
            {"error": {"message": f"无法连接模型服务：{exc}"}},
            ensure_ascii=False,
        )
        yield f"data: {err_line}\n\n"
        yield "data: [DONE]\n\n"


def complete_chat(
    *,
    url: str,
    api_key: str,
    messages: list[dict[str, str]],
    model: str,
    deep_think: bool,
) -> tuple[str, str, str | None]:
    used_model = _resolve_model(model, deep_think)
    if deep_think:
        return _complete_chat_stream_aggregate(
            url=url,
            api_key=api_key,
            messages=messages,
            used_model=used_model,
        )
    return _complete_chat_non_stream(
        url=url,
        api_key=api_key,
        messages=messages,
        used_model=used_model,
        deep_think=False,
    )
