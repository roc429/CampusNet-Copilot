import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.qwen_chat import SYSTEM_PROMPT, complete_chat, forward_dashscope_sse

router = APIRouter()


def _messages_with_system(body: ChatRequest) -> list[dict[str, str]]:
    trimmed: list[dict[str, str]] = []
    for m in body.messages[-40:]:
        c = m.content.strip()
        if not c:
            continue
        trimmed.append({"role": m.role, "content": c})

    if not trimmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有有效的对话内容",
        )

    return [{"role": "system", "content": SYSTEM_PROMPT}, *trimmed]


@router.post("/completions", response_model=ChatResponse)
def chat_completions(
    body: ChatRequest,
    _user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    settings = get_settings()
    if not settings.dashscope_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务器未配置 DASHSCOPE_API_KEY，无法调用大模型",
        )

    messages = _messages_with_system(body)

    content, used, reasoning = complete_chat(
        url=settings.dashscope_chat_url,
        api_key=settings.dashscope_api_key.strip(),
        messages=messages,
        model=body.model,
        deep_think=body.deep_think,
    )
    return ChatResponse(content=content, model=used, reasoning=reasoning)


@router.post("/completions/stream")
def chat_completions_stream(
    body: ChatRequest,
    _user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """SSE：透传百炼流式 chunk，便于前端打字机展示思考与正文。"""
    settings = get_settings()
    if not settings.dashscope_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务器未配置 DASHSCOPE_API_KEY，无法调用大模型",
        )

    messages = _messages_with_system(body)

    def gen() -> Iterator[str]:
        try:
            for piece in forward_dashscope_sse(
                url=settings.dashscope_chat_url,
                api_key=settings.dashscope_api_key.strip(),
                messages=messages,
                model=body.model,
                deep_think=body.deep_think,
            ):
                yield piece
        except Exception as exc:  # pragma: no cover
            err_line = json.dumps(
                {"error": {"message": str(exc)}},
                ensure_ascii=False,
            )
            yield f"data: {err_line}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
