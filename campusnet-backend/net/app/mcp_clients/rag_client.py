"""Knowledge base client facade."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass(slots=True)
class KnowledgeChunk:
    title: str
    content: str
    score: float
    source: str = "ops_manual"


_KNOWLEDGE_BASE: list[KnowledgeChunk] = [
    KnowledgeChunk(
        title="AP 负载过高处理",
        content="AP 负载通常由在线终端数、无线信道干扰、弱信号重传或异常大流量终端导致。建议先看在线终端数、信道利用率和上联口错误包。",
        score=0.92,
    ),
    KnowledgeChunk(
        title="丢包率含义",
        content="丢包率表示发送的数据包中未成功到达的比例。持续高丢包会表现为网页打开慢、语音视频卡顿或业务超时。",
        score=0.9,
    ),
    KnowledgeChunk(
        title="汇聚交换机职责",
        content="汇聚交换机连接多个接入交换机并上联核心层，常用于承载楼宇或区域流量汇总。",
        score=0.86,
    ),
    KnowledgeChunk(
        title="校园网认证失败排查",
        content="认证失败常见原因包括账号状态异常、终端缓存旧凭据、Portal 不可达、DHCP/DNS 异常或认证服务器链路异常。",
        score=0.84,
    ),
    KnowledgeChunk(
        title="宿舍区网络慢常见原因",
        content="宿舍区晚高峰网络慢通常与并发终端多、出口带宽利用率高、局部 AP 负载高、无线干扰或个别终端大流量有关。",
        score=0.88,
    ),
    KnowledgeChunk(
        title="设备问题与拥塞区分",
        content="如果多个下游设备同时丢包且上联带宽接近阈值，更偏向拥塞；如果单设备 CPU、错误包或重启异常突出，更偏向设备问题。",
        score=0.87,
    ),
]


async def search_knowledge_base(query: str, top_k: int = 5) -> list[KnowledgeChunk]:
    if not settings.rag_mock_enabled:
        return []

    terms = [term for term in query.replace("？", " ").replace("，", " ").split() if term]
    scored: list[KnowledgeChunk] = []
    for chunk in _KNOWLEDGE_BASE:
        haystack = f"{chunk.title} {chunk.content}"
        if any(term in haystack for term in terms) or any(key in query for key in chunk.title):
            scored.append(chunk)
    if not scored:
        scored = [chunk for chunk in _KNOWLEDGE_BASE if any(word in query for word in ["网络", "AP", "丢包", "认证", "链路"])]
    return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]
