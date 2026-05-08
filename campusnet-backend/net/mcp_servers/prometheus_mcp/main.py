"""Prometheus MCP Server。

Prometheus指标查询能力。

工具列表:
- get_device_metrics:  按设备 ID 列表查窗口内的连接数/CPU/丢包率(向后兼容旧 Campus MCP)。
- instant_query:       直接执行任意 PromQL,返回当前时刻的标量结果。
- range_query:         执行range PromQL,返回指定区间的时序数据。
- top_n_anomaly:       基于PromQL取Top-N 异常对象,供TelemetryAgent使用。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_servers._common.http import make_async_client
from mcp_servers._common.logging import configure_logging

logger = configure_logging("PrometheusMCP")


@dataclass(slots=True)
class PrometheusMCPSettings:
    """Prometheus MCP 配置。"""

    host: str = os.getenv("PROMETHEUS_MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("PROMETHEUS_MCP_PORT", "9001"))
    transport: str = os.getenv("PROMETHEUS_MCP_TRANSPORT", "sse")
    request_timeout_seconds: float = float(os.getenv("MCP_REQUEST_TIMEOUT_SECONDS", "8"))
    prometheus_base_url: str = os.getenv("PROMETHEUS_BASE_URL", "http://localhost:9090")


settings = PrometheusMCPSettings()

mcp = FastMCP(
    name="PrometheusMCP",
    host=settings.host,
    port=settings.port,
    log_level="INFO",
)


async def _query_prom_scalar(client: httpx.AsyncClient, query: str) -> float | None:
    """执行单点 PromQL,返回标量值。"""

    resp = await client.get(
        f"{settings.prometheus_base_url}/api/v1/query",
        params={"query": query},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "success":
        return None
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, TypeError, ValueError, IndexError):
        return None


async def _query_prom_raw(
    client: httpx.AsyncClient,
    endpoint: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """执行任意 Prometheus HTTP API,返回原始 JSON。"""

    resp = await client.get(f"{settings.prometheus_base_url}{endpoint}", params=params)
    resp.raise_for_status()
    return resp.json()


@mcp.tool(description="按设备 ID 列表查询近 N 分钟窗口内的连接数、CPU 负载、丢包率。")
async def get_device_metrics(
    device_ids: list[str],
    window_minutes: int = 10,
) -> dict[str, Any]:
    """Prometheus 指标采集工具。"""

    logger.info("Tool get_device_metrics called. device_ids=%s window=%dm", device_ids, window_minutes)
    if not device_ids:
        return {"ok": False, "error": "device_ids 不能为空"}

    window_minutes = max(1, int(window_minutes))
    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            metrics: list[dict[str, Any]] = []
            for device_id in device_ids:
                queries = {
                    "connections": f'avg_over_time(device_connections{{device_id="{device_id}"}}[{window_minutes}m])',
                    "cpu_load": f'avg_over_time(device_cpu_load{{device_id="{device_id}"}}[{window_minutes}m])',
                    "packet_loss": f'avg_over_time(device_packet_loss{{device_id="{device_id}"}}[{window_minutes}m])',
                }
                connections, cpu_load, packet_loss = await asyncio.gather(
                    _query_prom_scalar(client, queries["connections"]),
                    _query_prom_scalar(client, queries["cpu_load"]),
                    _query_prom_scalar(client, queries["packet_loss"]),
                )
                metrics.append(
                    {
                        "device_id": device_id,
                        "window": f"{window_minutes}m",
                        "connections": connections,
                        "cpu_load": cpu_load,
                        "packet_loss": packet_loss,
                    }
                )
    except httpx.TimeoutException:
        logger.exception("Tool get_device_metrics timeout.")
        return {"ok": False, "error": "Prometheus 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool get_device_metrics failed.")
        return {"ok": False, "error": f"Prometheus 查询失败: {exc}"}

    result = {"ok": True, "metrics": metrics}
    logger.info("Tool get_device_metrics returned ok=True, devices=%d", len(metrics))
    return result


@mcp.tool(description="执行任意 PromQL 即时查询,返回当前时刻的标量或向量结果。")
async def instant_query(promql: str) -> dict[str, Any]:
    """通用 PromQL 即时查询入口。"""

    logger.info("Tool instant_query called. promql=%s", promql)
    if not promql or not promql.strip():
        return {"ok": False, "error": "promql 不能为空"}

    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            payload = await _query_prom_raw(client, "/api/v1/query", {"query": promql})
    except httpx.TimeoutException:
        return {"ok": False, "error": "Prometheus 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool instant_query failed.")
        return {"ok": False, "error": f"Prometheus 查询失败: {exc}"}

    if payload.get("status") != "success":
        return {"ok": False, "error": payload.get("error", "Prometheus 返回非 success")}
    return {
        "ok": True,
        "promql": promql,
        "result_type": payload.get("data", {}).get("resultType"),
        "result": payload.get("data", {}).get("result", []),
    }


@mcp.tool(description="执行 PromQL 区间查询,返回 [start, end] 时间窗的时序点列表。")
async def range_query(
    promql: str,
    start_seconds_ago: int = 3600,
    end_seconds_ago: int = 0,
    step_seconds: int = 60,
) -> dict[str, Any]:
    """通用 PromQL range 查询入口。

    Args:
        promql: PromQL 表达式。
        start_seconds_ago: 起始时间相对now的秒数(正数,默认1小时前)。
        end_seconds_ago:   结束时间相对now的秒数(默认 0即now)。
        step_seconds:      采样步长,默认60秒。
    """

    logger.info(
        "Tool range_query called. promql=%s start=-%ds end=-%ds step=%ds",
        promql, start_seconds_ago, end_seconds_ago, step_seconds,
    )
    if not promql or not promql.strip():
        return {"ok": False, "error": "promql 不能为空"}
    if start_seconds_ago <= end_seconds_ago:
        return {"ok": False, "error": "start_seconds_ago 必须大于 end_seconds_ago"}

    now = time.time()
    params = {
        "query": promql,
        "start": now - start_seconds_ago,
        "end": now - end_seconds_ago,
        "step": max(1, int(step_seconds)),
    }

    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            payload = await _query_prom_raw(client, "/api/v1/query_range", params)
    except httpx.TimeoutException:
        return {"ok": False, "error": "Prometheus 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool range_query failed.")
        return {"ok": False, "error": f"Prometheus 查询失败: {exc}"}

    if payload.get("status") != "success":
        return {"ok": False, "error": payload.get("error", "Prometheus 返回非 success")}
    return {
        "ok": True,
        "promql": promql,
        "start": params["start"],
        "end": params["end"],
        "step": params["step"],
        "series": payload.get("data", {}).get("result", []),
    }


@mcp.tool(description="给定 PromQL 表达式,取 Top-N 数值最高的样本(用于异常排序)。")
async def top_n_anomaly(promql: str, n: int = 5) -> dict[str, Any]:
    """便捷的 Top-N 异常筛选工具。"""

    logger.info("Tool top_n_anomaly called. promql=%s n=%d", promql, n)
    if not promql or not promql.strip():
        return {"ok": False, "error": "promql 不能为空"}
    n = max(1, min(int(n), 50))

    wrapped = f"topk({n}, {promql})"
    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            payload = await _query_prom_raw(client, "/api/v1/query", {"query": wrapped})
    except httpx.TimeoutException:
        return {"ok": False, "error": "Prometheus 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool top_n_anomaly failed.")
        return {"ok": False, "error": f"Prometheus 查询失败: {exc}"}

    if payload.get("status") != "success":
        return {"ok": False, "error": payload.get("error", "Prometheus 返回非 success")}

    items = []
    for sample in payload.get("data", {}).get("result", []):
        metric = sample.get("metric", {})
        value = sample.get("value")
        if isinstance(value, list) and len(value) == 2:
            try:
                items.append({"labels": metric, "value": float(value[1])})
            except (TypeError, ValueError):
                continue
    return {"ok": True, "promql": promql, "top_n": n, "items": items}


if __name__ == "__main__":
    logger.info(
        "Starting PrometheusMCP. transport=%s host=%s port=%s prometheus=%s",
        settings.transport, settings.host, settings.port, settings.prometheus_base_url,
    )
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
