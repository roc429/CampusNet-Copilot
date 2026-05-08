"""Campus MCP Server (校内业务工具)。

端口默认 9000,与旧版 Campus MCP 保持兼容。
本阶段先暴露最小工具集:
- ping:       供 StandardMCPManager 健康探活与冒烟。
- echo:       排错时回显参数,验证 LangGraph -> MCP 链路。

后续将加入:
- create_workorder / query_workorder_status (工单衔接)
- simulate_in_sandbox (Mininet+Ryu 双回路外回路)
- kb_hybrid_search   (GraphRAG 桥接)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers._common.logging import configure_logging

logger = configure_logging("CampusMCP")


@dataclass(slots=True)
class CampusMCPSettings:
    """Campus MCP 配置。"""

    host: str = os.getenv("CAMPUS_MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("CAMPUS_MCP_PORT", "9000"))
    transport: str = os.getenv("CAMPUS_MCP_TRANSPORT", "sse")


settings = CampusMCPSettings()

mcp = FastMCP(
    name="CampusMCP",
    host=settings.host,
    port=settings.port,
    log_level="INFO",
)


@mcp.tool(description="健康探活,返回服务时间戳与版本号。")
async def ping() -> dict[str, Any]:
    """供 StandardMCPManager 监控系统检测可用性。"""

    return {
        "ok": True,
        "server": "CampusMCP",
        "version": "0.2.0",
        "timestamp": time.time(),
    }


@mcp.tool(description="回显输入参数,用于排查 LangGraph→MCP 调用链。")
async def echo(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """回显工具,便于调试。"""

    logger.info("Tool echo called. payload=%s", payload)
    return {
        "ok": True,
        "server": "CampusMCP",
        "received": payload or {},
    }


if __name__ == "__main__":
    logger.info(
        "Starting CampusMCP. transport=%s host=%s port=%s",
        settings.transport, settings.host, settings.port,
    )
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
