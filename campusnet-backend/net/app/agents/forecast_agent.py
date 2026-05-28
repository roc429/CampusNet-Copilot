"""ForecastAgent: periodic and on-demand future risk producer."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.mcp.client import get_standard_mcp_manager
from app.schemas import AnomalyEvent, ForecastQueryRequest
from app.stores import OpsMemoryStore


class ForecastAgent:
    """Generate future-risk signals with TimesFM MCP when enabled."""

    default_devices = ["AP-LIB-3F-02", "SW-LIB-AGG-01"]
    default_metrics = ["connections", "packet_loss", "cpu_load"]

    def __init__(
        self,
        anomaly_queue: asyncio.Queue[AnomalyEvent],
        store: OpsMemoryStore,
        interval_seconds: int = 900,
    ) -> None:
        self.anomaly_queue = anomaly_queue
        self.store = store
        self.interval_seconds = interval_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            if not settings.forecast_agent_enabled:
                continue
            try:
                await self.run_once(
                    ForecastQueryRequest(
                        device_ids=self.default_devices,
                        metrics=self.default_metrics,
                        horizon_minutes=120,
                        freq="5m",
                    ),
                    source="forecast_agent",
                    create_event=True,
                )
            except Exception:  # noqa: BLE001
                self.logger.exception("ForecastAgent periodic run failed")

    async def run_once(
        self,
        request: ForecastQueryRequest,
        source: str = "manual",
        create_event: bool = False,
    ) -> list[dict[str, Any]]:
        device_ids = request.device_ids or self.default_devices
        results: list[dict[str, Any]] = []
        for device_id in device_ids:
            for metric in request.metrics:
                result = await self._forecast_one(
                    device_id=device_id,
                    metric=metric,
                    horizon_minutes=request.horizon_minutes,
                    freq=request.freq,
                    source=source,
                )
                results.append(result)
                if create_event and self._is_risky(result):
                    await self._enqueue_forecast_event(result)
        return results

    async def _forecast_one(
        self,
        device_id: str,
        metric: str,
        horizon_minutes: int,
        freq: str,
        source: str,
    ) -> dict[str, Any]:
        key = f"{device_id}:{metric}:{horizon_minutes}:{freq}"
        cached = self.store.forecast_results.get(key)
        if cached and cached.get("valid_until", "") > datetime.now(timezone.utc).isoformat():
            return {**cached, "cache_status": "hit"}
        if key in self.store.forecast_locks:
            return cached or {"forecast_key": key, "status": "running"}

        self.store.forecast_locks.add(key)
        try:
            payload = await self._call_timesfm(device_id, metric, horizon_minutes, freq)
            result = {
                "forecast_key": key,
                "device_id": device_id,
                "metric": metric,
                "horizon_minutes": horizon_minutes,
                "freq": freq,
                "source": source,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                "payload": payload,
                "risk_level": self._risk_level(metric, payload),
            }
            self.store.save_forecast(key, result)
            return result
        finally:
            self.store.forecast_locks.discard(key)

    async def _call_timesfm(self, device_id: str, metric: str, horizon_minutes: int, freq: str) -> dict[str, Any]:
        manager = get_standard_mcp_manager()
        result = await manager.call_remote_tool(
            server_name="timesfm",
            tool_name="forecast_metric",
            arguments={
                "device_id": device_id,
                "metric": metric,
                "horizon_minutes": horizon_minutes,
                "freq": freq,
            },
        )
        structured = result.get("structured_content")
        return structured if isinstance(structured, dict) else result

    @staticmethod
    def _risk_level(metric: str, payload: dict[str, Any]) -> str:
        forecast = payload.get("forecast", [])
        values = [float(value) for value in forecast if isinstance(value, int | float)]
        peak = max(values) if values else 0.0
        if metric == "packet_loss" and peak >= 0.05:
            return "critical"
        if metric in {"connections", "cpu_load"} and peak >= 90:
            return "warning"
        return "normal"

    @staticmethod
    def _is_risky(result: dict[str, Any]) -> bool:
        return result.get("risk_level") in {"warning", "critical"}

    async def _enqueue_forecast_event(self, result: dict[str, Any]) -> None:
        event = AnomalyEvent(
            event_type="timesfm_forecast_anomaly",
            source="forecast",
            device_id=str(result.get("device_id")),
            metric=str(result.get("metric")),
            severity=result.get("risk_level", "warning"),
            issue_desc=f"预测到 {result.get('device_id')} 的 {result.get('metric')} 存在未来风险。",
            metadata={"forecast": result},
        )
        self.store.save_event(event)
        await self.anomaly_queue.put(event)
        self.logger.info("Forecast anomaly enqueued event_id=%s", event.event_id)

