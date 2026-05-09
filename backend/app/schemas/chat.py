from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=32000)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=80)
    model: Literal["qwen-flash", "qwen-plus", "qwen-max"] = "qwen-flash"
    deep_think: bool = False


class ChatResponse(BaseModel):
    content: str
    model: str
    # 深度思考 + 流式时由后端聚合；否则为 None
    reasoning: str | None = None
