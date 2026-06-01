"""基于官方 MCP SDK 的标准客户端管理器。"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPServerEndpoint:
    """MCP Server 连接配置。"""

    name: str
    sse_url: str


@dataclass(slots=True)
class RemoteToolInfo:
    """远程工具元数据。"""

    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


class StandardMCPManager:
    """标准 MCP 多服务管理器。

    关键能力：
    - 同时连接多个 MCP Server（SSE 协议）
    - 动态发现工具列表
    - 统一执行远程工具调用
    """

    def __init__(
        self,
        endpoints: list[MCPServerEndpoint],
        timeout_seconds: float = 10.0,
        sse_read_timeout_seconds: float = 300.0,
        trust_env: bool = False,
    ) -> None:
        self.endpoints = endpoints
        self.timeout_seconds = timeout_seconds
        self.sse_read_timeout_seconds = sse_read_timeout_seconds
        self.trust_env = trust_env

        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._connected = False
        self._session_transport: dict[str, str] = {}

    @classmethod
    def from_settings(cls) -> StandardMCPManager:
        """从全局配置构造默认管理器。

        按设计文档 §3.4.1 / §3.4.2 的"即插即用"原则,枚举所有已知的 MCP
        端点配置,只把非空 URL 注册到 manager。新增 MCP Server 时,
        只需在 settings 里加一项配置 + 部署对应 server,即可零代码接入。
        """

        candidates: list[tuple[str, str]] = [
            ("netbox", settings.netbox_mcp_sse_url),
            ("campus", settings.campus_mcp_sse_url),
            ("prometheus", settings.prometheus_mcp_sse_url),
            ("grafana", settings.grafana_mcp_sse_url),
            ("timesfm", settings.timesfm_mcp_sse_url),
        ]
        endpoints = [
            MCPServerEndpoint(name=name, sse_url=url.strip())
            for name, url in candidates
            if url and url.strip()
        ]
        if not endpoints:
            logger.warning(
                "No MCP endpoint configured. Diagnosis graph will run LLM-only."
            )
        else:
            logger.info(
                "MCP endpoints registered: %s",
                ", ".join(f"{ep.name}={ep.sse_url}" for ep in endpoints),
            )
        return cls(
            endpoints=endpoints,
            timeout_seconds=float(settings.request_timeout),
            sse_read_timeout_seconds=float(settings.mcp_sse_read_timeout),
            trust_env=not settings.disable_env_proxy,
        )

    @asynccontextmanager
    async def _httpx_factory(self, *, headers: dict[str, Any] | None = None, auth: httpx.Auth | None = None, timeout: httpx.Timeout | None = None):
        """为 mcp.sse_client 提供可控的 HTTPX 客户端。"""

        async with httpx.AsyncClient(
            headers=headers,
            auth=auth,
            timeout=timeout,
            trust_env=self.trust_env,
        ) as client:
            yield client

    @staticmethod
    def _streamable_url_from_sse_url(sse_url: str) -> str:
        """把 `/sse` 端点推导为 `/mcp`。"""

        if sse_url.endswith("/sse"):
            return f"{sse_url[:-4]}/mcp"
        return sse_url

    async def connect(self) -> None:
        """建立到全部 MCP Server 的会话连接。"""

        if self._connected:
            return

        self._stack = AsyncExitStack()
        self._sessions = {}

        logger.info("MCP manager connecting to %d servers ...", len(self.endpoints))
        for endpoint in self.endpoints:
            endpoint_stack = AsyncExitStack()
            try:
                logger.info("Connecting MCP server: %s -> %s", endpoint.name, endpoint.sse_url)
                try:
                    read_stream, write_stream = await endpoint_stack.enter_async_context(
                        sse_client(
                            endpoint.sse_url,
                            timeout=self.timeout_seconds,
                            sse_read_timeout=self.sse_read_timeout_seconds,
                            httpx_client_factory=self._httpx_factory,
                        )
                    )
                    session = await endpoint_stack.enter_async_context(
                        ClientSession(
                            read_stream,
                            write_stream,
                            read_timeout_seconds=timedelta(seconds=self.sse_read_timeout_seconds),
                        )
                    )
                    init_result = await asyncio.wait_for(
                        session.initialize(),
                        timeout=self.timeout_seconds,
                    )
                    logger.info(
                        "MCP handshake success (sse): server=%s protocol=%s server_name=%s",
                        endpoint.name,
                        init_result.protocolVersion,
                        init_result.serverInfo.name,
                    )
                    self._sessions[endpoint.name] = session
                    self._session_transport[endpoint.name] = "sse"
                    if self._stack is not None:
                        await self._stack.enter_async_context(endpoint_stack.pop_all())
                    continue
                except BaseException as exc:
                    try:
                        await endpoint_stack.aclose()
                    except BaseException:
                        logger.debug("SSE endpoint stack close failed: %s", endpoint.name)
                    endpoint_stack = AsyncExitStack()
                    logger.warning(
                        "SSE connect failed for server=%s, trying streamable-http fallback: %s",
                        endpoint.name,
                        f"{type(exc).__name__}: {exc}",
                    )

                streamable_url = self._streamable_url_from_sse_url(endpoint.sse_url)
                http_client = await endpoint_stack.enter_async_context(
                    httpx.AsyncClient(
                        timeout=self.timeout_seconds,
                        trust_env=self.trust_env,
                    )
                )
                read_stream, write_stream, _ = await endpoint_stack.enter_async_context(
                    streamable_http_client(
                        streamable_url,
                        http_client=http_client,
                    )
                )
                session = await endpoint_stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(seconds=self.sse_read_timeout_seconds),
                    )
                )
                init_result = await asyncio.wait_for(
                    session.initialize(),
                    timeout=self.timeout_seconds,
                )
                logger.info(
                    "MCP handshake success (streamable-http): server=%s protocol=%s server_name=%s endpoint=%s",
                    endpoint.name,
                    init_result.protocolVersion,
                    init_result.serverInfo.name,
                    streamable_url,
                )
                self._sessions[endpoint.name] = session
                self._session_transport[endpoint.name] = "streamable-http"
                if self._stack is not None:
                    await self._stack.enter_async_context(endpoint_stack.pop_all())
            except BaseException as exc:
                logger.warning(
                    "MCP server connect failed: %s error=%s",
                    endpoint.name,
                    f"{type(exc).__name__}: {exc}",
                )
                try:
                    await endpoint_stack.aclose()
                except BaseException:
                    logger.warning("MCP endpoint stack close failed after endpoint error: %s", endpoint.name)

        self._connected = True
        logger.info("MCP manager connected. active_sessions=%s", list(self._sessions.keys()))

    async def close(self) -> None:
        """关闭全部 MCP 会话。"""

        if self._stack is not None:
            try:
                await self._stack.aclose()
            except BaseException:  # noqa: BLE001
                logger.exception("MCP manager close encountered errors, force clearing sessions.")
        self._stack = None
        self._sessions = {}
        self._session_transport = {}
        self._connected = False
        logger.info("MCP manager closed.")

    async def list_remote_tools(self) -> list[RemoteToolInfo]:
        """动态发现所有远程工具。"""

        await self.connect()
        tools: list[RemoteToolInfo] = []
        for server_name, session in self._sessions.items():
            logger.info("Discovering tools from MCP server: %s", server_name)
            cursor: str | None = None
            while True:
                result = await asyncio.wait_for(
                    session.list_tools(cursor=cursor),
                    timeout=self.timeout_seconds,
                )
                for remote_tool in result.tools:
                    tools.append(
                        RemoteToolInfo(
                            server_name=server_name,
                            name=remote_tool.name,
                            description=remote_tool.description or "",
                            input_schema=remote_tool.inputSchema,
                        )
                    )
                cursor = result.nextCursor
                if not cursor:
                    break
            logger.info(
                "Tool discovery done: server=%s discovered=%d",
                server_name,
                len([t for t in tools if t.server_name == server_name]),
            )
        return tools

    async def call_remote_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用指定服务器上的远程工具。"""

        await self.connect()
        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"MCP server session not found: {server_name}")

        args = arguments or {}
        logger.info(
            "Calling remote tool: server=%s tool=%s args=%s",
            server_name,
            tool_name,
            json.dumps(args, ensure_ascii=False),
        )

        result = await asyncio.wait_for(
            session.call_tool(name=tool_name, arguments=args),
            timeout=self.timeout_seconds,
        )

        content_items: list[Any] = []
        text_fragments: list[str] = []
        for item in result.content:
            dumped = item.model_dump(by_alias=True)
            content_items.append(dumped)
            if dumped.get("type") == "text" and isinstance(dumped.get("text"), str):
                text_fragments.append(dumped["text"])

        payload: dict[str, Any] = {
            "ok": not bool(result.isError),
            "server_name": server_name,
            "tool_name": tool_name,
            "structured_content": result.structuredContent,
            "content": content_items,
        }
        if text_fragments:
            payload["text"] = "\n".join(text_fragments)

        logger.info(
            "Remote tool returned: server=%s tool=%s ok=%s",
            server_name,
            tool_name,
            payload["ok"],
        )
        return payload


_global_mcp_manager: StandardMCPManager | None = None


def get_standard_mcp_manager() -> StandardMCPManager:
    """获取全局复用的 MCP 管理器实例。"""

    global _global_mcp_manager
    if _global_mcp_manager is None:
        _global_mcp_manager = StandardMCPManager.from_settings()
    return _global_mcp_manager
