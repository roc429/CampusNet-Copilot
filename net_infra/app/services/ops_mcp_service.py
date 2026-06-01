"""Unified MCP service APIs used by FastAPI routes and LangGraph tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.mcp.client import StandardMCPManager, get_standard_mcp_manager
from app.schemas import OpsMetricsResponse

logger = logging.getLogger(__name__)


class OpsMCPService:
    """Thin facade over StandardMCPManager.

    The service keeps transport details out of FastAPI routes and exposes a
    stable metrics shape for agents that should not depend on Prometheus labels.
    """

    def __init__(self, manager: StandardMCPManager | None = None) -> None:
        self.manager = manager or get_standard_mcp_manager()

    async def health(self) -> dict[str, Any]:
        """Return configured MCP servers, active sessions, transports and tools."""

        try:
            tools = await self.manager.list_remote_tools()
        except Exception as exc:  # noqa: BLE001
            logger.exception("MCP health check failed.")
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "servers": [
                    {"server_name": endpoint.name, "endpoint": endpoint.sse_url, "connected": False}
                    for endpoint in self.manager.endpoints
                ],
            }

        tool_count_by_server: dict[str, int] = {}
        tool_names_by_server: dict[str, list[str]] = {}
        for tool in tools:
            tool_count_by_server[tool.server_name] = tool_count_by_server.get(tool.server_name, 0) + 1
            tool_names_by_server.setdefault(tool.server_name, []).append(tool.name)

        sessions = getattr(self.manager, "_sessions", {})
        transports = getattr(self.manager, "_session_transport", {})
        return {
            "ok": True,
            "servers": [
                {
                    "server_name": endpoint.name,
                    "endpoint": endpoint.sse_url,
                    "connected": endpoint.name in sessions,
                    "transport": transports.get(endpoint.name),
                    "tool_count": tool_count_by_server.get(endpoint.name, 0),
                    "tools": tool_names_by_server.get(endpoint.name, []),
                }
                for endpoint in self.manager.endpoints
            ],
        }

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call one remote MCP tool through the shared StandardMCPManager."""

        return await self.manager.call_remote_tool(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments or {},
        )

    async def get_device_metrics(self, device_id: str, window: str = "5m") -> OpsMetricsResponse:
        """Fetch normalized real-time telemetry metrics for one device.

        Prometheus fixtures in this project have used both `device_id` and
        `device` labels, so each metric tries both before marking it missing.
        """

        metric_candidates: dict[str, list[str]] = {
            "ap_load": ["device_ap_load", "ap_load"],
            "packet_loss": ["device_packet_loss", "packet_loss"],
            "latency": ["device_latency", "network_latency_ms", "latency"],
            "bandwidth_usage": ["device_bandwidth_usage", "bandwidth_usage_percent", "device_bandwidth_out"],
            "cpu_load": ["device_cpu_load", "cpu_load"],
            "connections": ["device_connections", "connections", "wifi_clients"],
        }

        values: dict[str, float | None] = {}
        raw_queries: dict[str, str] = {}
        missing: list[str] = []
        source = "prometheus_mcp"

        for field_name, candidates in metric_candidates.items():
            value, promql = await self._query_first_value(device_id=device_id, candidates=candidates, window=window)
            values[field_name] = value
            if promql:
                raw_queries[field_name] = promql
            if value is None:
                missing.append(field_name)

        if len(missing) == len(metric_candidates):
            source = "prometheus_mcp_empty"

        return OpsMetricsResponse(
            device_id=device_id,
            source=source,
            missing_metrics=missing,
            raw_queries=raw_queries,
            **values,
        )

    async def _query_first_value(
        self,
        device_id: str,
        candidates: list[str],
        window: str,
    ) -> tuple[float | None, str | None]:
        for metric_name in candidates:
            for label_name in ("device_id", "device"):
                promql = f'{metric_name}{{{label_name}="{device_id}"}}'
                value = await self._instant_value(promql)
                if value is not None:
                    return value, promql

                avg_promql = f'avg_over_time({metric_name}{{{label_name}="{device_id}"}}[{window}])'
                avg_value = await self._instant_value(avg_promql)
                if avg_value is not None:
                    return avg_value, avg_promql
        return None, None

    async def _instant_value(self, promql: str) -> float | None:
        try:
            payload = await self.call_tool("prometheus", "instant_query", {"promql": promql})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Prometheus MCP instant query failed. promql=%s error=%s", promql, exc)
            return None

        structured = self._extract_structured_payload(payload)
        result = structured.get("result")
        if not isinstance(result, list) or not result:
            return None

        first = result[0]
        if not isinstance(first, dict):
            return None
        sample = first.get("value")
        if not isinstance(sample, list) or len(sample) < 2:
            return None
        try:
            return float(sample[1])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
        structured = payload.get("structured_content")
        if isinstance(structured, dict):
            return structured

        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}
