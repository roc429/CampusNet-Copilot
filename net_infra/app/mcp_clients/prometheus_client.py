"""Prometheus MCP client facade."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.mcp.client import get_standard_mcp_manager

logger = logging.getLogger(__name__)

_PROM_METRIC_NAMES = {
    "packet_loss": "device_packet_loss",
    "cpu_load": "device_cpu_load",
    "connections": "device_connections",
    "bandwidth_in": "device_bandwidth_in",
    "bandwidth_out": "device_bandwidth_out",
    "ap_load": "device_ap_load",
    "latency": "device_latency",
    "interface_errors": "device_interface_errors",
}

_MOCK_METRICS: dict[str, dict[str, float]] = {
    "AP-LIB-01": {"packet_loss": 0.018, "bandwidth_in": 68.0, "bandwidth_out": 72.0, "ap_load": 91.0, "cpu_load": 62.0, "connections": 116.0, "latency": 38.0, "interface_errors": 1.0},
    "AP-LIB-01": {"packet_loss": 0.011, "bandwidth_in": 42.0, "bandwidth_out": 45.0, "ap_load": 74.0, "cpu_load": 51.0, "connections": 82.0, "latency": 29.0, "interface_errors": 0.0},
    "SW-TEACH-01": {"packet_loss": 0.004, "bandwidth_in": 71.0, "bandwidth_out": 72.0, "ap_load": 0.0, "cpu_load": 44.0, "connections": 0.0, "latency": 16.0, "interface_errors": 0.0},
    "AP-DORM-A1": {"packet_loss": 0.036, "bandwidth_in": 86.0, "bandwidth_out": 89.0, "ap_load": 88.0, "cpu_load": 69.0, "connections": 138.0, "latency": 55.0, "interface_errors": 2.0},
    "SW-DORM-01": {"packet_loss": 0.028, "bandwidth_in": 92.0, "bandwidth_out": 94.0, "ap_load": 0.0, "cpu_load": 57.0, "connections": 0.0, "latency": 48.0, "interface_errors": 1.0},
}


async def get_metric_current(device_id: str, metric: str) -> dict[str, Any]:
    prom_metric = _PROM_METRIC_NAMES.get(metric, metric)
    promql = f'{prom_metric}{{device_id="{device_id}"}}'
    return await _query_single_metric(device_id=device_id, metric=metric, promql=promql, value_kind="current")


async def get_metric_avg(device_id: str, metric: str, window: str = "5m") -> dict[str, Any]:
    # Prefer the tested high-level MCP tool for the three core metrics it exposes.
    if metric in {"connections", "cpu_load", "packet_loss"}:
        bulk_value = await _get_device_metrics_value(device_id, metric, window)
        if bulk_value["value"] is not None:
            return bulk_value

    prom_metric = _PROM_METRIC_NAMES.get(metric, metric)
    promql = f'avg_over_time({prom_metric}{{device_id="{device_id}"}}[{window}])'
    return await _query_single_metric(device_id=device_id, metric=metric, promql=promql, window=window, value_kind="avg")


async def get_metric_max(device_id: str, metric: str, window: str = "30m") -> dict[str, Any]:
    prom_metric = _PROM_METRIC_NAMES.get(metric, metric)
    promql = f'max_over_time({prom_metric}{{device_id="{device_id}"}}[{window}])'
    return await _query_single_metric(device_id=device_id, metric=metric, promql=promql, window=window, value_kind="max")


async def get_metric_trend(device_id: str, metric: str, window: str = "30m") -> dict[str, Any]:
    prom_metric = _PROM_METRIC_NAMES.get(metric, metric)
    promql = f'{prom_metric}{{device_id="{device_id}"}}'
    try:
        result = await query_promql_range(promql, window=window)
        return {"device_id": device_id, "metric": metric, "window": window, "trend": _trend_from_series(result)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prometheus MCP trend query failed, using unknown trend. device_id=%s metric=%s error=%s", device_id, metric, exc)
        return {"device_id": device_id, "metric": metric, "window": window, "trend": "unknown"}


async def query_promql(promql: str) -> dict[str, Any]:
    manager = get_standard_mcp_manager()
    try:
        result = await manager.call_remote_tool(
            server_name="prometheus",
            tool_name="instant_query",
            arguments={"promql": promql},
        )
    except BaseException as exc:  # noqa: BLE001
        await manager.close()
        raise RuntimeError(f"Prometheus MCP instant_query failed: {type(exc).__name__}: {exc}") from exc
    payload = _extract_payload(result)
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or payload))
    return payload if isinstance(payload, dict) else {"result": payload}


async def query_promql_range(promql: str, window: str = "30m") -> dict[str, Any]:
    seconds = _window_to_seconds(window)
    manager = get_standard_mcp_manager()
    try:
        result = await manager.call_remote_tool(
            server_name="prometheus",
            tool_name="range_query",
            arguments={
                "promql": promql,
                "start_seconds_ago": seconds,
                "end_seconds_ago": 0,
                "step_seconds": 60,
            },
        )
    except BaseException as exc:  # noqa: BLE001
        await manager.close()
        raise RuntimeError(f"Prometheus MCP range_query failed: {type(exc).__name__}: {exc}") from exc
    payload = _extract_payload(result)
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or payload))
    return payload if isinstance(payload, dict) else {"series": payload}


async def _get_device_metrics_value(device_id: str, metric: str, window: str) -> dict[str, Any]:
    try:
        manager = get_standard_mcp_manager()
        try:
            result = await manager.call_remote_tool(
                server_name="prometheus",
                tool_name="get_device_metrics",
                arguments={"device_ids": [device_id], "window_minutes": max(1, _window_to_seconds(window) // 60)},
            )
        except BaseException as exc:  # noqa: BLE001
            await manager.close()
            raise RuntimeError(f"Prometheus MCP get_device_metrics failed: {type(exc).__name__}: {exc}") from exc
        payload = _extract_payload(result)
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise RuntimeError(str(payload.get("error") or payload))
        metrics = payload.get("metrics", []) if isinstance(payload, dict) else []
        if metrics and isinstance(metrics[0], dict):
            return {
                "device_id": device_id,
                "metric": metric,
                "window": window,
                "value": metrics[0].get(metric),
                "status": "ok",
                "source": "prometheus_mcp.get_device_metrics",
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prometheus MCP get_device_metrics failed. device_id=%s metric=%s error=%s", device_id, metric, exc)
    return _mock_metric(device_id, metric, window=window, source="mock_fallback")


async def _query_single_metric(
    device_id: str,
    metric: str,
    promql: str,
    window: str | None = None,
    value_kind: str = "current",
) -> dict[str, Any]:
    try:
        payload = await query_promql(promql)
        value = _first_prometheus_value(payload)
        if value is not None:
            response = {
                "device_id": device_id,
                "metric": metric,
                "value": value,
                "status": "ok",
                "source": "prometheus_mcp.instant_query",
                "promql": promql,
                "value_kind": value_kind,
            }
            if window:
                response["window"] = window
            return response
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prometheus MCP metric query failed. device_id=%s metric=%s promql=%s error=%s", device_id, metric, promql, exc)
    return _mock_metric(device_id, metric, window=window, source="mock_fallback", promql=promql)


def _extract_payload(envelope: dict[str, Any]) -> Any:
    structured = envelope.get("structured_content")
    if structured:
        return structured
    text = envelope.get("text")
    if isinstance(text, str) and text.strip():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
    return envelope


def _first_prometheus_value(payload: dict[str, Any]) -> float | None:
    result = payload.get("result", [])
    if not isinstance(result, list) or not result:
        return None
    value = result[0].get("value") if isinstance(result[0], dict) else None
    if isinstance(value, list) and len(value) >= 2:
        try:
            return float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _trend_from_series(payload: dict[str, Any]) -> str:
    series = payload.get("series", [])
    if not isinstance(series, list) or not series:
        return "unknown"
    values = series[0].get("values", []) if isinstance(series[0], dict) else []
    if len(values) < 2:
        return "unknown"
    try:
        first = float(values[0][1])
        last = float(values[-1][1])
    except (TypeError, ValueError, IndexError):
        return "unknown"
    if last > first * 1.1:
        return "rising"
    if last < first * 0.9:
        return "falling"
    return "stable"


def _window_to_seconds(window: str) -> int:
    stripped = window.strip().lower()
    if stripped.endswith("m"):
        return int(stripped[:-1]) * 60
    if stripped.endswith("h"):
        return int(stripped[:-1]) * 3600
    if stripped.endswith("s"):
        return int(stripped[:-1])
    return int(stripped)


def _mock_metric(
    device_id: str,
    metric: str,
    window: str | None = None,
    source: str = "mock_fallback",
    promql: str | None = None,
) -> dict[str, Any]:
    value = _MOCK_METRICS.get(device_id.upper(), {}).get(metric)
    response = {
        "device_id": device_id,
        "metric": metric,
        "value": value,
        "status": "ok" if value is not None else "unknown",
        "source": source,
    }
    if window:
        response["window"] = window
    if promql:
        response["promql"] = promql
    return response
